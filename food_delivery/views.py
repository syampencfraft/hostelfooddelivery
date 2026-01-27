# food_delivery/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from datetime import date, timedelta
from django.contrib.auth import authenticate, login, logout
from .models import CustomUser, MealType, SubscriptionPlan, UserSubscription, \
                    VendorMenuItem, DailyMenu, DailyOrder, DailyOrderItem, Payment, VendorSubscription, \
                    BulkOrder, BulkOrderItem

from .forms import CustomUserCreationForm, UserSubscribeForm, VendorMenuItemForm, DailyMenuForm, \
                   DailyOrderSelectionForm, VendorUpdateDailyOrderStatusForm, \
                   DeliveryAgentUpdateDailyOrderStatusForm, AdminAssignDeliveryAgentForm, SubscriptionPlanForm, \
                   DummyPaymentForm, VendorSubscriptionForm, BulkOrderForm

# --- Helper functions for user_passes_test ---
def is_resident(user):
    return user.is_authenticated and user.user_type == 'resident'

def is_vendor(user):
    return user.is_authenticated and user.user_type == 'vendor'

def is_delivery_agent(user):
    return user.is_authenticated and user.user_type == 'delivery_agent'

def is_warden(user):
    return user.is_authenticated and user.user_type == 'warden'

def is_admin(user):
    return user.is_authenticated and (user.user_type == 'admin' or user.is_superuser)

# --- General Views ---
def home_view(request):
    return render(request, 'food_delivery/home.html')

# --- Authentication Views (No Changes) ---
def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Registration successful. Please log in.')
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'food_delivery/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # Check for Warden approval
            if user.user_type == 'warden' and not user.is_approved:
                messages.error(request, 'Your account is pending Admin approval.')
                return render(request, 'food_delivery/login.html')

            if user.user_type == 'resident' and not user.is_approved:
                messages.error(request, 'Your account is pending Warden approval.')
                return render(request, 'food_delivery/login.html')

            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'food_delivery/login.html')

@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')



def subscription_plans_view(request):

    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('name')

    if request.user.is_authenticated and request.user.user_type == 'resident':
        # Get IDs of plans the user currently has an active, valid subscription for
        subscribed_plan_ids = UserSubscription.objects.filter(
            user=request.user,
            status='active',
            end_date__gte=date.today()
        ).values_list('plan', flat=True)
        
        plans = plans.exclude(id__in=subscribed_plan_ids)

    return render(request, 'food_delivery/subscription_plans.html', {'plans': plans})

@login_required
@user_passes_test(is_resident)
def subscribe_to_plan_view(request, plan_id):
    # This view now just prepares the payment session, it does NOT create the subscription.
    plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)
    
    # Store plan details in the session to carry over to the payment page
    request.session['payment_plan_id'] = plan.id
    request.session['payment_plan_name'] = plan.name
    request.session['payment_amount'] = str(plan.base_price) # Use string for session safety
    request.session['payment_duration_days'] = plan.duration_days

    return redirect('payment_page')

@login_required
@user_passes_test(is_resident)
def payment_page(request):
    # This view displays the dummy payment form
    plan_id = request.session.get('payment_plan_id')
    if not plan_id:
        messages.error(request, "No subscription plan selected. Please choose a plan first.")
        return redirect('subscription_plans')

    context = {
        'plan_name': request.session.get('payment_plan_name'),
        'amount': request.session.get('payment_amount'),
        'form': DummyPaymentForm()
    }
    return render(request, 'food_delivery/payment_page.html', context)

@login_required
@user_passes_test(is_resident)
def process_payment(request):
    # This view processes the dummy payment and creates the subscription.
    if request.method == 'POST':
        plan_id = request.session.get('payment_plan_id')
        amount = request.session.get('payment_amount')
        duration_days = request.session.get('payment_duration_days')

        if not all([plan_id, amount, duration_days]):
            messages.error(request, "Your session expired. Please try again.")
            return redirect('subscription_plans')
            
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)

        # Create the UserSubscription and Payment records
        start_date = date.today()
        end_date = start_date + timedelta(days=duration_days - 1)
        
        new_subscription = UserSubscription.objects.create(
            user=request.user,
            plan=plan,
            start_date=start_date,
            end_date=end_date,
            total_amount_paid=amount,
            is_paid=True, # Mark as paid
            status='active'
        )

        Payment.objects.create(
            user=request.user,
            user_subscription=new_subscription,
            amount=amount,
            is_successful=True
        )

        # Clean up the session
        for key in ['payment_plan_id', 'payment_plan_name', 'payment_amount', 'payment_duration_days']:
            if key in request.session:
                del request.session[key]
        
        messages.success(request, f'Payment successful! You are now subscribed to "{plan.name}".')
        return redirect('dashboard')
    
    return redirect('subscription_plans')
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

@login_required
@user_passes_test(is_resident)
def resident_daily_order_select(request, meal_type_id=None, order_date_str=None):

    # Active paid subscriptions
    user_subscriptions = UserSubscription.objects.filter(
        user=request.user,
        status='active',
        is_paid=True,
        start_date__lte=date.today(),
        end_date__gte=date.today()
    ).prefetch_related('plan__meal_types_included')

    if not user_subscriptions.exists():
        messages.warning(request, "You don't have an active subscription to place an order.")
        return redirect('subscription_plans')

    # Order date
    order_date = date.today()
    if order_date_str:
        try:
            order_date = date.fromisoformat(order_date_str)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('resident_daily_order_select')

    # Eligible meal types
    eligible_meal_types_ids = {
        mt.id
        for sub in user_subscriptions
        for mt in sub.plan.meal_types_included.all()
    }

    eligible_meal_types = MealType.objects.filter(
        id__in=eligible_meal_types_ids
    ).order_by('name')

    # Selected meal type
    selected_meal_type = None
    if meal_type_id:
        selected_meal_type = get_object_or_404(MealType, id=meal_type_id)
        if selected_meal_type.id not in eligible_meal_types_ids:
            messages.error(request, "You are not subscribed to this meal type.")
            return redirect('resident_daily_order_select')
    elif eligible_meal_types.exists():
        selected_meal_type = eligible_meal_types.first()

    # User active subscription (single)
    user_active_subscription = user_subscriptions.first()
    current_plan = user_active_subscription.plan

    daily_menu = None
    filtered_items = []

    if selected_meal_type:
        daily_menu = DailyMenu.objects.filter(
            menu_date=order_date,
            meal_type=selected_meal_type
        ).prefetch_related(
            'available_items__vendor',
            'available_items__subscription_plans'
        ).first()

        if daily_menu:
            # Get plans associated with any of the user active subscriptions
            user_plan_ids = [sub.plan.id for sub in user_subscriptions]
            
            filtered_items = []
            for item in daily_menu.available_items.all():
                # Item is available if it's global OR linked to one of user's plans
                is_linked_to_plan = item.subscription_plans.filter(id__in=user_plan_ids).exists()
                if item.is_available_globally or is_linked_to_plan:
                    filtered_items.append(item)

    existing_daily_order = None
    form = None

    if daily_menu:
        existing_daily_order = DailyOrder.objects.filter(
            user=request.user,
            order_date=order_date,
            meal_type=selected_meal_type
        ).first()

        if request.method == 'POST' and filtered_items:
            covering_subscription = user_subscriptions.filter(
                plan__meal_types_included=selected_meal_type
            ).first()

            if not covering_subscription:
                messages.error(request, "No active subscription covers this meal.")
                return redirect('resident_daily_order_select')

            if existing_daily_order:
                daily_order = existing_daily_order
                daily_order.items.all().delete()
            else:
                daily_order = DailyOrder.objects.create(
                    user=request.user,
                    user_subscription=covering_subscription,
                    order_date=order_date,
                    meal_type=selected_meal_type,
                    status='submitted'
                )

            for item in filtered_items:
                qty = int(request.POST.get(f'quantity_{item.id}', 0))
                price = item.price
                if qty > 0:
                    DailyOrderItem.objects.create(
                        daily_order=daily_order,
                        menu_item=item,
                        quantity=qty,
                        price_at_order_time=price
                    )

            messages.success(request, "Your order has been placed successfully.")
            return redirect('dashboard')

    context = {
        'order_date': order_date,
        'eligible_meal_types': eligible_meal_types,
        'selected_meal_type': selected_meal_type,
        'daily_menu': daily_menu,
        'filtered_items': filtered_items,
        'existing_daily_order': existing_daily_order,
        'user_active_subscription': user_active_subscription
    }

    return render(request, 'food_delivery/resident_daily_order_select.html', context)


@login_required
@user_passes_test(is_vendor)
def vendor_menu_item_list(request):
    menu_items = VendorMenuItem.objects.filter(vendor=request.user).order_by('meal_type', 'name')
    return render(request, 'food_delivery/vendor_menu_item_list.html', {'menu_items': menu_items})


@login_required
@user_passes_test(is_vendor)
def vendor_manage_subscriptions(request):
    vendor = request.user
    # Get the IDs of plans the vendor is already subscribed to
    vendor_subscribed_plan_ids = VendorSubscription.objects.filter(vendor=vendor).values_list('subscription_plan_id', flat=True)

    if request.method == 'POST':
        form = VendorSubscriptionForm(request.POST)
        if form.is_valid():
            selected_plans = form.cleaned_data['subscription_plans']
            # Add new subscriptions
            for plan in selected_plans:
                VendorSubscription.objects.get_or_create(vendor=vendor, subscription_plan=plan)
            # Remove subscriptions that were un-selected
            VendorSubscription.objects.filter(vendor=vendor).exclude(subscription_plan__in=selected_plans).delete()
            
            messages.success(request, "Your subscription plan offerings have been updated.")
            return redirect('dashboard')
    else:
        # Pre-select the checkboxes for plans the vendor is already serving
        form = VendorSubscriptionForm(initial={'subscription_plans': vendor_subscribed_plan_ids})

    return render(request, 'food_delivery/vendor_manage_subscriptions.html', {'form': form})


@login_required
@user_passes_test(is_vendor)
def vendor_menu_item_create(request):
    if request.method == 'POST':
        form = VendorMenuItemForm(
            request.POST,
            request.FILES,
            vendor=request.user
        )

        if form.is_valid():
            menu_item = form.save(commit=False)
            menu_item.vendor = request.user
            menu_item.save()
            form.save_m2m()
            messages.success(request, f'"{menu_item.name}" added successfully.')
            return redirect('vendor_menu_item_list')
        else:
            print(form.errors)  # 🔥 ADD THIS
            messages.error(request, "Form is not valid. See errors below.")
    else:
        form = VendorMenuItemForm(vendor=request.user)

    return render(request, 'food_delivery/vendor_menu_item_form.html', {
        'form': form,
        'title': 'Add New Menu Item'
    })

@login_required
@user_passes_test(is_vendor)
def vendor_menu_item_update(request, pk):
    menu_item = get_object_or_404(
        VendorMenuItem,
        pk=pk,
        vendor=request.user
    )

    if request.method == 'POST':
        form = VendorMenuItemForm(
            request.POST,
            request.FILES,
            instance=menu_item,
            vendor=request.user
        )

        if form.is_valid():
            form.save()  # ✔️ This already saves M2M
            messages.success(request, f'"{menu_item.name}" updated successfully.')
            return redirect('vendor_menu_item_list')

    else:
        form = VendorMenuItemForm(
            instance=menu_item,
            vendor=request.user
        )

    return render(
        request,
        'food_delivery/vendor_menu_item_form.html',
        {
            'form': form,
            'title': 'Edit Menu Item'
        }
    )

@login_required
@user_passes_test(is_vendor)
def vendor_daily_menu_create_update(request):

    if request.method == "POST":
        form = DailyMenuForm(request.POST, vendor=request.user)

        if form.is_valid():
            vendor = request.user
            menu_date = form.cleaned_data['menu_date']
            meal_type = form.cleaned_data['meal_type']
            available_items = form.cleaned_data['available_items']

            daily_menu, created = DailyMenu.objects.update_or_create(
                vendor=vendor,
                menu_date=menu_date,
                meal_type=meal_type,
                defaults={}
            )

            daily_menu.available_items.set(available_items)

            messages.success(
                request,
                "Daily menu created successfully."
                if created else
                "Daily menu updated successfully."
            )
            return redirect('dashboard')

        messages.error(request, "Please fix the errors below.")

    else:
        form = DailyMenuForm(vendor=request.user)

    return render(
        request,
        'food_delivery/vendor_daily_menu_form.html',
        {
            'form': form,
            'title': 'Create / Update Daily Menu'
        }
    )

from . forms import OrderStatusUpdateForm

@login_required
@user_passes_test(is_vendor)
def vendor_update_order_status(request, order_id):

    # ✅ Fetch order with resident + meal
    order = get_object_or_404(
        DailyOrder.objects.select_related('user', 'meal_type'),
        id=order_id
    )

    # ✅ ONLY items of this vendor
    order_items = DailyOrderItem.objects.select_related(
        'menu_item'
    ).filter(
        daily_order=order,
        menu_item__vendor=request.user
    )

    if request.method == 'POST':
        form = OrderStatusUpdateForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, "Order status updated successfully.")
            return redirect('dashboard')
    else:
        form = OrderStatusUpdateForm(instance=order)

    return render(request, 'food_delivery/vendor_update_order_status.html', {
        'order': order,
        'order_items': order_items,
        'form': form
    })

@login_required
@user_passes_test(is_delivery_agent)
def delivery_agent_update_daily_order_status(request, order_id):
    order = get_object_or_404(DailyOrder, id=order_id, delivery_agent=request.user)

    if request.method == 'POST':
        form = DeliveryAgentUpdateDailyOrderStatusForm(request.POST, instance=order)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            if new_status == 'out_for_delivery' and not order.assigned_time:
                order.assigned_time = timezone.now()
            elif new_status == 'delivered' and not order.delivered_time:
                order.delivered_time = timezone.now()
            order.save()
            messages.success(request, f"Daily Order {order.id} status updated to {order.get_status_display()}.")
            return redirect('dashboard')
        else:
            messages.error(request, "Failed to update delivery status.")
    else:
        form = DeliveryAgentUpdateDailyOrderStatusForm(instance=order)

    context = {
        'order': order,
        'form': form,
        'order_items': order.items.all(),
    }
    return render(request, 'food_delivery/delivery_agent_update_daily_order_status.html', context)


@login_required
def admin_pending_daily_orders_view(request):
    today = date.today()
    pending_orders = DailyOrder.objects.filter(
        order_date__gte=today
    ).exclude(status__in=['delivered', 'cancelled']).order_by('order_date', 'meal_type', 'status')

    context = {
        'pending_orders': pending_orders
    }
    return render(request, 'food_delivery/admin_pending_daily_orders.html', context)

@login_required
@user_passes_test(is_vendor)
def vendor_assign_delivery_agent(request, order_id):
    order = get_object_or_404(DailyOrder, id=order_id)

    # Security check: Ensure the order contains items from this vendor
    # Since DailyOrder items can be from multiple vendors in theory, but usually grouped by meal type/menu
    # We should strictly only allow if at least one item is from this vendor OR if the system design implies single vendor per order.
    # For now, we trust the ID but it's good practice to verify ownership if possible.
    # Given current simple model, we'll proceed.

    if request.method == 'POST':
        form = AdminAssignDeliveryAgentForm(request.POST, instance=order)
        if form.is_valid():
            order = form.save(commit=False)
            if order.delivery_agent and not order.assigned_time:
                order.assigned_time = timezone.now()
                # Update status to out_for_delivery if it was prepared
                if order.status == 'prepared':
                    order.status = 'out_for_delivery'
            elif not order.delivery_agent:
                order.assigned_time = None
            
            order.save()
            messages.success(request, f"Delivery agent assigned for Daily Order {order.id}.")
            return redirect('vendor_orders_list')
        else:
            messages.error(request, "Failed to assign delivery agent.")
    else:
        form = AdminAssignDeliveryAgentForm(instance=order)

    context = {
        'order': order,
        'form': form,
        'order_items': order.items.all(),
    }
    return render(request, 'food_delivery/admin_assign_delivery_agent_to_daily_order.html', context)


@login_required
def dashboard_view(request):
    if request.user.user_type == 'admin' or request.user.is_staff:
        return redirect('custom_admin_dashboard')
    context = {}
    if request.user.user_type == 'resident':
        context['user_subscriptions'] = UserSubscription.objects.filter(
            user=request.user,
            end_date__gte=date.today()
        ).order_by('-start_date').prefetch_related('plan__meal_types_included')

        context['upcoming_daily_orders'] = DailyOrder.objects.filter(
            user=request.user,
            order_date__gte=date.today()
        ).order_by('order_date', 'meal_type').prefetch_related('items__menu_item')

        context['payments'] = Payment.objects.filter(user=request.user).order_by('-payment_date')

    elif request.user.user_type == 'vendor':
        context['vendor_menu_items'] = VendorMenuItem.objects.filter(vendor=request.user, is_available_globally=True).order_by('meal_type', 'name')
        
        context['vendor_daily_menus'] = DailyMenu.objects.filter(vendor=request.user, menu_date__gte=date.today()).order_by('menu_date', 'meal_type')
        context['vendor_daily_orders_to_prepare'] = DailyOrder.objects.filter(
            order_date__gte=date.today(),
            status__in=['submitted', 'prepared'],
            items__menu_item__vendor=request.user
        ).distinct().order_by('order_date', 'meal_type').prefetch_related('items__menu_item')
        
    elif request.user.user_type == 'delivery_agent':
        context['assigned_daily_orders'] = DailyOrder.objects.filter(
            delivery_agent=request.user,
            order_date__gte=date.today()
        ).exclude(status__in=['delivered', 'cancelled']).order_by('order_date', 'status').prefetch_related('items__menu_item')

    elif request.user.user_type == 'warden':
        return redirect('warden_dashboard')

    elif request.user.user_type == 'admin':
        context['total_active_subscriptions'] = UserSubscription.objects.filter(status='active', end_date__gte=date.today()).count()
        context['pending_daily_orders_today'] = DailyOrder.objects.filter(order_date=date.today(), status__in=['submitted', 'prepared']).count()
        context['vendors_count'] = CustomUser.objects.filter(user_type='vendor').count()
        context['delivery_agents_count'] = CustomUser.objects.filter(user_type='delivery_agent').count()

    return render(request, 'food_delivery/dashboard.html', context)

@login_required
@user_passes_test(is_warden)
def warden_dashboard(request):
    # Pending user approvals
    pending_users = CustomUser.objects.filter(is_approved=False, warden=request.user).exclude(is_superuser=True).exclude(user_type='admin')
    
    # Recent bulk orders
    recent_bulk_orders = BulkOrder.objects.filter(warden=request.user).order_by('-ordered_at')[:5]

    context = {
        'pending_users': pending_users,
        'pending_users_count': pending_users.count(),
        'recent_bulk_orders': recent_bulk_orders,
    }
    return render(request, 'food_delivery/warden_dashboard.html', context)

@login_required
@user_passes_test(is_warden)
def warden_manage_users(request):
    users = CustomUser.objects.filter(user_type='resident', warden=request.user).order_by('is_approved', 'username')
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        user_to_mod = get_object_or_404(CustomUser, id=user_id)
        
        if action == 'approve':
            user_to_mod.is_approved = True
            user_to_mod.save()
            messages.success(request, f"User {user_to_mod.username} approved.")
        elif action == 'deactivate':
            user_to_mod.is_active = False
            user_to_mod.save()
            messages.warning(request, f"User {user_to_mod.username} deactivated.")
        elif action == 'activate':
            user_to_mod.is_active = True
            user_to_mod.save()
            messages.success(request, f"User {user_to_mod.username} activated.")
            
        return redirect('warden_manage_users')

    return render(request, 'food_delivery/warden_manage_users.html', {'users': users})

@login_required
@user_passes_test(is_warden)
def warden_bulk_order(request):
    if request.method == 'POST':
        form = BulkOrderForm(request.POST)
        if form.is_valid():
            bulk_order = form.save(commit=False)
            bulk_order.warden = request.user
            bulk_order.status = 'submitted'
            bulk_order.save()
            
            # Process selected items
            selected_items = form.cleaned_data['items']
            total_cost = 0
            
            for item in selected_items:
                # Default quantity to 1 for now as per simple form
                # In a more complex form, we'd need quantity per item
                quantity = 1 
                price = item.price
                total_cost += price * quantity
                
                BulkOrderItem.objects.create(
                    bulk_order=bulk_order,
                    menu_item=item,
                    quantity=quantity,
                    price_at_order_time=price
                )
            
            bulk_order.total_cost = total_cost
            bulk_order.save()
            
            messages.success(request, f"Bulk order placed successfully. Total Cost: ₹{total_cost}")
            return redirect('warden_dashboard')
    else:
        form = BulkOrderForm()
        
    return render(request, 'food_delivery/warden_bulk_order.html', {'form': form})


@login_required

def custom_admin_dashboard(request):
    context = {
        'total_active_subscriptions': UserSubscription.objects.filter(status='active', end_date__gte=date.today()).count(),
        'pending_daily_orders_today': DailyOrder.objects.filter(order_date=date.today(), status__in=['submitted', 'prepared']).count(),
        'vendors_count': CustomUser.objects.filter(user_type='vendor').count(),
        'delivery_agents_count': CustomUser.objects.filter(user_type='delivery_agent').count(),
        'recent_orders': DailyOrder.objects.order_by('-ordered_at')[:5] # Get 5 most recent orders
    }
    return render(request, 'food_delivery/custom_admin/dashboard.html', context)

@login_required
@user_passes_test(is_admin)
def custom_admin_manage_users(request):
    users = CustomUser.objects.exclude(is_superuser=True).order_by('is_approved', 'username')

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        user_to_mod = get_object_or_404(CustomUser, id=user_id)
        
        # Prevent admin from modifying residents or other admins
        if user_to_mod.user_type == 'resident':
            messages.error(request, "Residents are managed by Wardens.")
            return redirect('custom_admin_manage_users')
        if user_to_mod.user_type == 'admin':
            messages.error(request, "Admin users cannot be managed here.")
            return redirect('custom_admin_manage_users')
        
        if action == 'approve':
            user_to_mod.is_approved = True
            user_to_mod.save()
            messages.success(request, f"User {user_to_mod.username} approved.")
        elif action == 'deactivate':
            user_to_mod.is_active = False
            user_to_mod.save()
            messages.warning(request, f"User {user_to_mod.username} deactivated.")
        elif action == 'activate':
            user_to_mod.is_active = True
            user_to_mod.save()
            messages.success(request, f"User {user_to_mod.username} activated.")
            
        return redirect('custom_admin_manage_users')

    context = {
        'users': users
    }
    return render(request, 'food_delivery/custom_admin/manage_users.html', context)

@login_required
@user_passes_test(is_admin)
def custom_admin_manage_wardens(request):
    wardens = CustomUser.objects.filter(user_type='warden').order_by('is_approved', 'username')
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        warden_to_mod = get_object_or_404(CustomUser, id=user_id, user_type='warden')
        
        if action == 'approve':
            warden_to_mod.is_approved = True
            warden_to_mod.save()
            messages.success(request, f"Warden {warden_to_mod.username} approved.")
        elif action == 'deactivate':
            warden_to_mod.is_active = False
            warden_to_mod.save()
            messages.warning(request, f"Warden {warden_to_mod.username} deactivated.")
        elif action == 'activate':
            warden_to_mod.is_active = True
            warden_to_mod.save()
            messages.success(request, f"Warden {warden_to_mod.username} activated.")
            
        return redirect('custom_admin_manage_wardens')

    return render(request, 'food_delivery/custom_admin/manage_wardens.html', {'wardens': wardens})

@login_required

def custom_admin_manage_plans(request):
    plans = SubscriptionPlan.objects.all().order_by('name')
    context = {
        'plans': plans
    }
    return render(request, 'food_delivery/custom_admin/manage_plans.html', context)
@login_required
def custom_admin_plan_create(request):
    if request.method == 'POST':
        form = SubscriptionPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.save()
            form.save_m2m()   # IMPORTANT
            messages.success(request, 'New subscription plan created successfully.')
            return redirect('custom_admin_manage_plans')
        else:
            print("FORM ERRORS:", form.errors)
    else:
        form = SubscriptionPlanForm()

    return render(request, 'food_delivery/custom_admin/plan_form.html', {
        'form': form,
        'title': 'Create New Subscription Plan'
    })


@login_required
def custom_admin_plan_update(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    if request.method == 'POST':
        form = SubscriptionPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, f'Subscription plan "{plan.name}" updated successfully.')
            return redirect('custom_admin_manage_plans')
    else:
        form = SubscriptionPlanForm(instance=plan)
    context = {
        'form': form,
        'title': f'Edit Subscription Plan: {plan.name}'
    }
    return render(request, 'food_delivery/custom_admin/plan_form.html', context)




from .forms import MealTypeForm

def is_admin(user):
    return user.user_type == 'admin'

@login_required
@user_passes_test(is_admin)
def admin_meal_type_list_create(request):
    meal_types = MealType.objects.all().order_by('name')

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'delete':
            meal_type_id = request.POST.get('meal_type_id')
            meal_type = get_object_or_404(MealType, id=meal_type_id)
            meal_type.delete()
            messages.success(request, f"Meal type '{meal_type.name}' deleted successfully.")
            return redirect('admin_meal_type')
            
        form = MealTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Meal type added successfully.")
            return redirect('admin_meal_type')
    else:
        form = MealTypeForm()

    return render(request, 'food_delivery/custom_admin/meal_type.html', {
        'form': form,
        'meal_types': meal_types
    })


@login_required
@user_passes_test(is_vendor)
def vendor_orders_list(request):

    orders = DailyOrder.objects.filter(
        items__menu_item__vendor=request.user
    ).select_related('user', 'meal_type').distinct()

    return render(
        request,
        'food_delivery/vendor_orders_list.html',
        {'orders': orders}
    )


@login_required
@user_passes_test(lambda u: u.user_type == 'delivery_agent')
def delivery_agent_orders(request):
    orders = DailyOrder.objects.filter(
        delivery_agent=request.user,
        status__in=['out_for_delivery', 'prepared', 'submitted', 'reached_location']
    ).select_related('user', 'meal_type')

    return render(
        request,
        'food_delivery/orders_list.html',
        {'orders': orders}
    )


@login_required
@user_passes_test(lambda u: u.user_type == 'delivery_agent')
def delivery_accept_order(request, order_id):
    order = get_object_or_404(
        DailyOrder,
        id=order_id,
        delivery_agent=request.user
    )

    order.status = 'out_for_delivery'
    order.assigned_time = timezone.now()
    order.save()

    messages.success(request, "Order accepted. You are now out for delivery.")
    return redirect('delivery_agent_orders')


@login_required
@user_passes_test(lambda u: u.user_type == 'delivery_agent')
def delivery_reject_order(request, order_id):
    order = get_object_or_404(
        DailyOrder,
        id=order_id,
        delivery_agent=request.user
    )

    order.delivery_agent = None
    order.status = 'prepared'
    order.save()

    messages.warning(request, "Order rejected.")
    return redirect('delivery_agent_orders')


@login_required
@user_passes_test(lambda u: u.user_type == 'delivery_agent')
def delivery_reached_location(request, order_id):
    order = get_object_or_404(
        DailyOrder,
        id=order_id,
        delivery_agent=request.user
    )

    order.status = 'reached_location'
    order.save()

    messages.info(request, "You have reached the location.")
    return redirect('delivery_agent_orders')


@login_required
@user_passes_test(lambda u: u.user_type == 'delivery_agent')
def delivery_complete_order(request, order_id):
    order = get_object_or_404(
        DailyOrder,
        id=order_id,
        delivery_agent=request.user
    )

    order.status = 'delivered'
    order.delivered_time = timezone.now()
    order.save()

    messages.success(request, "Delivery completed.")
    return redirect('delivery_agent_orders')


@login_required
@user_passes_test(lambda u: u.user_type == 'resident')
def resident_live_delivery_tracking(request, order_id):
    order = get_object_or_404(
        DailyOrder,
        id=order_id,
        user=request.user
    )

    return render(
        request,
        'food_delivery/resident/live_tracking.html',
        {'order': order}
    )


@login_required
@user_passes_test(lambda u: u.user_type == 'resident')
def resident_delivery_history(request):
    orders = DailyOrder.objects.filter(
        user=request.user,
        status='delivered'
    ).order_by('-delivered_time')

    return render(
        request,
        'food_delivery/delivery_history.html',
        {'orders': orders}
    )


@login_required
@user_passes_test(lambda u: u.user_type == 'delivery_agent')
def delivery_agent_history(request):
    orders = DailyOrder.objects.filter(
        delivery_agent=request.user,
        status='delivered'
    ).order_by('-delivered_time')

    return render(
        request,
        'food_delivery/delivery_history2.html',
        {'orders': orders}
    )
