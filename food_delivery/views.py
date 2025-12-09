# food_delivery/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from datetime import date, timedelta
from django.contrib.auth import authenticate, login, logout
from .models import CustomUser, MealType, SubscriptionPlan, UserSubscription, \
                    VendorMenuItem, DailyMenu, DailyOrder, DailyOrderItem, Payment, VendorSubscription

from .forms import CustomUserCreationForm, UserSubscribeForm, VendorMenuItemForm, DailyMenuForm, \
                   DailyOrderSelectionForm, VendorUpdateDailyOrderStatusForm, \
                   DeliveryAgentUpdateDailyOrderStatusForm, AdminAssignDeliveryAgentForm, SubscriptionPlanForm, DummyPaymentForm, VendorSubscriptionForm

# --- Helper functions for user_passes_test ---
def is_resident(user):
    return user.is_authenticated and user.user_type == 'resident'

def is_vendor(user):
    return user.is_authenticated and user.user_type == 'vendor'

def is_delivery_agent(user):
    return user.is_authenticated and user.user_type == 'delivery_agent'

def is_admin(user):
    return user.is_authenticated and user.is_staff and user.is_superuser

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

@login_required
@user_passes_test(is_resident)
def resident_daily_order_select(request, meal_type_id=None, order_date_str=None):

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

    order_date = date.today()
    if order_date_str:
        try:
            order_date = date.fromisoformat(order_date_str)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('resident_daily_order_select')


    eligible_meal_types_ids = set()
    for sub in user_subscriptions:
        for mt in sub.plan.meal_types_included.all():
            eligible_meal_types_ids.add(mt.id)

    eligible_meal_types = MealType.objects.filter(id__in=eligible_meal_types_ids).order_by('name')

  
    selected_meal_type = None
    if meal_type_id:
        selected_meal_type = get_object_or_404(MealType, id=meal_type_id)
        if selected_meal_type.id not in eligible_meal_types_ids:
            messages.error(request, f"You are not subscribed to {selected_meal_type.name} meals.")
            return redirect('resident_daily_order_select')
    elif eligible_meal_types.exists():
        selected_meal_type = eligible_meal_types.first() 

    user_active_subscription = UserSubscription.objects.filter(
        user=request.user,
        status='active',
        start_date__lte=date.today(),
        end_date__gte=date.today()
    ).first() # For simplicity, assume one active subscription. Real-world might need more logic.

    if not user_active_subscription:
        messages.warning(request, "You don't have an active subscription.")
        return redirect('subscription_plans')
    
    current_plan = user_active_subscription.plan

    daily_menu = None
    if selected_meal_type:
        # Find a daily menu from ANY vendor for this date and meal type
        daily_menu_query = DailyMenu.objects.filter(
            menu_date=order_date,
            meal_type=selected_meal_type
        ).prefetch_related('available_items__vendor', 'available_items__subscription_plans')
        
        daily_menu = daily_menu_query.first()
        
        if daily_menu:
            # ## CRUCIAL NEW LOGIC ##
            # Filter the menu items to only show those valid for the user's current plan
            original_items = daily_menu.available_items.all()
            filtered_items = [item for item in original_items if current_plan in item.subscription_plans.all()]
            
            # We pass the filtered items to the form/template
            # A bit of a hack: we modify the daily_menu object in memory for the template
            daily_menu.filtered_available_items = filtered_items

    daily_menu = None
    if selected_meal_type:
      
        daily_menu_query = DailyMenu.objects.filter(
            menu_date=order_date,
            meal_type=selected_meal_type
        ).prefetch_related('available_items__vendor')
        
        daily_menu = daily_menu_query.first() 

    form = None
    existing_daily_order = None
    if daily_menu:
  
        existing_daily_order = DailyOrder.objects.filter(
            user=request.user,
            order_date=order_date,
            meal_type=selected_meal_type
        ).first()

        if existing_daily_order and existing_daily_order.status not in ['pending', 'submitted']:
            messages.info(request, f"You have already placed and confirmed your {selected_meal_type.name} order for {order_date}. Status: {existing_daily_order.get_status_display()}.")
            form = None 
        else:
            if request.method == 'POST':
                form = DailyOrderSelectionForm(request.POST, daily_menu=daily_menu)
                if form.is_valid():
                
                    covering_subscription = user_subscriptions.filter(
                        plan__meal_types_included=selected_meal_type
                    ).first() 

                    if not covering_subscription:
                        messages.error(request, "No active subscription covers this meal type.")
                        return redirect('resident_daily_order_select', meal_type_id=meal_type_id, order_date_str=order_date_str)

                    if existing_daily_order:
                        # Update existing order
                        daily_order = existing_daily_order
                        daily_order.status = 'submitted'
                        daily_order.save()
                        daily_order.items.all().delete() 
                    else:
                        # Create new daily order
                        daily_order = DailyOrder.objects.create(
                            user=request.user,
                            user_subscription=covering_subscription,
                            order_date=order_date,
                            meal_type=selected_meal_type,
                            status='submitted'
                        )

                    for item in daily_menu.available_items.all():
                        quantity = form.cleaned_data.get(f'quantity_{item.id}', 0)
                        price_at_order_time = form.cleaned_data.get(f'price_{item.id}', item.price)
                        if quantity > 0:
                            DailyOrderItem.objects.create(
                                daily_order=daily_order,
                                menu_item=item,
                                quantity=quantity,
                                price_at_order_time=price_at_order_time
                            )
                    messages.success(request, f"Your {selected_meal_type.name} order for {order_date} has been placed!")
                    return redirect('dashboard')
                else:
                    messages.error(request, "Please correct the errors in your selection.")
            else:
                initial_data = {}
                if existing_daily_order:
    
                    for order_item in existing_daily_order.items.all():
                        initial_data[f'quantity_{order_item.menu_item.id}'] = order_item.quantity
                form = DailyOrderSelectionForm(daily_menu=daily_menu, initial=initial_data)
    else:
        messages.info(request, f"No menu available for {selected_meal_type.name} on {order_date}. Please check later or select another meal type.")

    context = {
        'order_date': order_date,
        'eligible_meal_types': eligible_meal_types,
        'selected_meal_type': selected_meal_type,
        'daily_menu': daily_menu,
        'form': form,
        'existing_daily_order': existing_daily_order
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
        form = VendorMenuItemForm(request.POST, request.FILES, vendor=request.user) # Pass vendor to the form
        if form.is_valid():
            menu_item = form.save(commit=False)
            menu_item.vendor = request.user
            menu_item.save()
            form.save_m2m() # Important for ManyToMany fields
            messages.success(request, f'"{menu_item.name}" added to your menu items.')
            return redirect('vendor_menu_item_list')
    else:
        form = VendorMenuItemForm(vendor=request.user) # Pass vendor to the form
    return render(request, 'food_delivery/vendor_menu_item_form.html', {'form': form, 'title': 'Add New Menu Item'})

@login_required
@user_passes_test(is_vendor)
def vendor_menu_item_update(request, pk):
    menu_item = get_object_or_404(VendorMenuItem, pk=pk, vendor=request.user)
    if request.method == 'POST':
        form = VendorMenuItemForm(request.POST, request.FILES, instance=menu_item, vendor=request.user) # Pass vendor
        if form.is_valid():
            form.save()
            form.save_m2m() # Important for ManyToMany fields
            messages.success(request, f'"{menu_item.name}" updated.')
            return redirect('vendor_menu_item_list')
    else:
        form = VendorMenuItemForm(instance=menu_item, vendor=request.user) # Pass vendor
    return render(request, 'food_delivery/vendor_menu_item_form.html', {'form': form, 'title': 'Edit Menu Item'})

@login_required
@user_passes_test(is_vendor)
def vendor_daily_menu_create_update(request, menu_date_str=None, meal_type_id=None):

    menu_date = date.today()
    if menu_date_str:
        try:
            menu_date = date.fromisoformat(menu_date_str)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('vendor_daily_menu_create_update')

    meal_type = None
    if meal_type_id:
        meal_type = get_object_or_404(MealType, id=meal_type_id)
    

    instance = None
    if meal_type:
        instance = DailyMenu.objects.filter(vendor=request.user, menu_date=menu_date, meal_type=meal_type).first()

    if request.method == 'POST':
        form = DailyMenuForm(request.POST, instance=instance, vendor=request.user)
        if form.is_valid():
            daily_menu = form.save(commit=False)
            daily_menu.vendor = request.user
            if not instance: 
                 daily_menu.meal_type = form.cleaned_data['meal_type'] 
            daily_menu.save()
            form.save_m2m() 
            messages.success(request, f'Daily Menu for {daily_menu.meal_type.name} on {daily_menu.menu_date} updated.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Failed to update Daily Menu. Please correct errors.')
    else:
        initial_data = {'menu_date': menu_date}
        if meal_type:
            initial_data['meal_type'] = meal_type.id
        form = DailyMenuForm(instance=instance, vendor=request.user, initial=initial_data)

    context = {
        'form': form,
        'title': 'Create/Update Daily Menu',
        'menu_date': menu_date,
        'meal_type': meal_type,
        'all_meal_types': MealType.objects.all(),
    }
    return render(request, 'food_delivery/vendor_daily_menu_form.html', context)


@login_required
@user_passes_test(is_vendor)
def vendor_update_daily_order_status(request, order_id):
    order = get_object_or_404(DailyOrder, id=order_id)     
    order_items_from_this_vendor = DailyOrderItem.objects.filter(
        daily_order=order,
        menu_item__vendor=request.user
    ).exists()

    if not order_items_from_this_vendor:
        messages.error(request, "You are not authorized to update this order.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = VendorUpdateDailyOrderStatusForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, f"Daily Order {order.id} status updated to {order.get_status_display()}.")
            return redirect('dashboard')
        else:
            messages.error(request, "Failed to update daily order status.")
    else:
        form = VendorUpdateDailyOrderStatusForm(instance=order)

    context = {
        'order': order,
        'form': form,
        'order_items': order.items.filter(menu_item__vendor=request.user),
    }
    return render(request, 'food_delivery/vendor_update_daily_order_status.html', context)


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
def admin_assign_delivery_agent_to_daily_order(request, order_id):
    order = get_object_or_404(DailyOrder, id=order_id)

    if request.method == 'POST':
        form = AdminAssignDeliveryAgentForm(request.POST, instance=order)
        if form.is_valid():
            order = form.save(commit=False)
            if order.delivery_agent and not order.assigned_time:
                order.assigned_time = timezone.now()
            elif not order.delivery_agent:
                order.assigned_time = None
            order.save()
            messages.success(request, f"Delivery agent assigned for Daily Order {order.id}.")
            return redirect('admin_pending_daily_orders')
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

    elif request.user.user_type == 'admin':
        context['total_active_subscriptions'] = UserSubscription.objects.filter(status='active', end_date__gte=date.today()).count()
        context['pending_daily_orders_today'] = DailyOrder.objects.filter(order_date=date.today(), status__in=['submitted', 'prepared']).count()
        context['vendors_count'] = CustomUser.objects.filter(user_type='vendor').count()
        context['delivery_agents_count'] = CustomUser.objects.filter(user_type='delivery_agent').count()

    return render(request, 'food_delivery/dashboard.html', context)

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

def custom_admin_manage_users(request):
    users = CustomUser.objects.exclude(is_superuser=True).order_by('username')
    context = {
        'users': users
    }
    return render(request, 'food_delivery/custom_admin/manage_users.html', context)

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
            form.save()
            messages.success(request, 'New subscription plan created successfully.')
            return redirect('custom_admin_manage_plans')
    else:
        form = SubscriptionPlanForm()
    context = {
        'form': form,
        'title': 'Create New Subscription Plan'
    }
    return render(request, 'food_delivery/custom_admin/plan_form.html', context)

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