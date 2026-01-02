# food_delivery/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from datetime import date, timedelta
from .models import CustomUser, SubscriptionPlan, UserSubscription, \
                    VendorMenuItem, DailyMenu, DailyOrder, DailyOrderItem, MealType

# --- User Authentication Forms (No Changes) ---
class CustomUserCreationForm(UserCreationForm):
    user_type = forms.ChoiceField(choices=CustomUser.USER_TYPE_CHOICES, initial='resident')
    phone_number = forms.CharField(max_length=15, required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + ('user_type', 'phone_number', 'address',)

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = UserChangeForm.Meta.fields

# --- 1. Resident Subscription Form (Updated) ---
class UserSubscribeForm(forms.Form):
    # This form now selects a SubscriptionPlan and its duration if variable
    # For simplicity, we assume SubscriptionPlan has a fixed duration_days.
    # So the form mainly confirms the plan.

    # If you had plans with flexible durations (e.g., "Monthly" or "Weekly" for same plan)
    # you'd add a duration field here. For now, plan.duration_days is fixed.
    
    # We pass the selected plan_id via URL, so this form is simple.
    pass # No fields needed, just a confirmation.

# --- 2. Vendor Forms ---

class VendorSubscriptionForm(forms.Form):
    # Form for vendor to select which plans they want to serve
    subscription_plans = forms.ModelMultipleChoiceField(
        queryset=SubscriptionPlan.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        label="Select the subscription plans you want to provide meals for"
    )

class VendorMenuItemForm(forms.ModelForm):
    # We must modify this form to only show plans the vendor has subscribed to.
    class Meta:
        model = VendorMenuItem
        fields = ['name', 'description', 'price', 'meal_type', 'subscription_plans', 'image', 'is_available_globally']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'subscription_plans': forms.CheckboxSelectMultiple, # Make it user-friendly
        }

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None) # Get the vendor from the view
        super().__init__(*args, **kwargs)
        if vendor:
            # THIS IS THE KEY LOGIC:
            # Only show subscription plans that this vendor has opted-in to serve.
            self.fields['subscription_plans'].queryset = SubscriptionPlan.objects.filter(
                vendorsubscription__vendor=vendor,
                vendorsubscription__is_active=True
            )

class DailyMenuForm(forms.ModelForm):
    # This form will allow a vendor to select multiple items for a daily menu
    available_items = forms.ModelMultipleChoiceField(
        queryset=VendorMenuItem.objects.none(), # Will be set in __init__
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Select items for this menu"
    )
    
    class Meta:
        model = DailyMenu
        fields = ['menu_date', 'meal_type', 'available_items']
        widgets = {
            'menu_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
        if vendor:
            # Filter available items to only those belonging to this vendor
            self.fields['available_items'].queryset = VendorMenuItem.objects.filter(vendor=vendor, is_available_globally=True)
            
        # Limit meal_type choices to the ones defined in MealType model
        self.fields['meal_type'].queryset = MealType.objects.all()

# --- 3. Resident Daily Order Selection Form ---
# This form will be dynamically generated in the view based on DailyMenu items
class DailyOrderSelectionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        daily_menu = kwargs.pop('daily_menu')
        super().__init__(*args, **kwargs)

        self.menu_items = daily_menu.available_items.all()
        for item in self.menu_items:
            # Create a quantity field for each item
            self.fields[f'quantity_{item.id}'] = forms.IntegerField(
                min_value=0,
                max_value=10, # Max quantity a user can order for one item
                initial=0,
                required=False, # Make it not strictly required, so 0 is valid
                label=f'{item.name} (₹{item.price})',
                widget=forms.NumberInput(attrs={'class': 'quantity-input'})
            )
            # You might want to add a hidden field for the price at order time for each item
            self.fields[f'price_{item.id}'] = forms.DecimalField(
                initial=item.price,
                widget=forms.HiddenInput(),
                required=True
            )

    def clean(self):
        cleaned_data = super().clean()
        has_selection = False
        for item in self.menu_items:
            quantity = cleaned_data.get(f'quantity_{item.id}', 0)
            if quantity and quantity > 0:
                has_selection = True
                break
        
        if not has_selection:
            raise forms.ValidationError("Please select at least one item to order.")
        
        return cleaned_data

# --- 4. Status Update Forms (Adapted for DailyOrder) ---
class VendorUpdateDailyOrderStatusForm(forms.ModelForm):
    class Meta:
        model = DailyOrder
        fields = ['status']
        widgets = {
            'status': forms.Select(choices=[
                ('prepared', 'Prepared'),
                ('cancelled', 'Cancelled by Vendor')
            ])
        }

class DeliveryAgentUpdateDailyOrderStatusForm(forms.ModelForm):
    class Meta:
        model = DailyOrder
        fields = ['status']
        widgets = {
            'status': forms.Select(choices=[
                ('out_for_delivery', 'Out for Delivery'),
                ('delivered', 'Delivered'),
                ('cancelled', 'Cancelled by Delivery Agent')
            ])
        }

class AdminAssignDeliveryAgentForm(forms.ModelForm):
    # This form will be used by Admin to assign an agent to a DailyOrder
    class Meta:
        model = DailyOrder
        fields = ['delivery_agent']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['delivery_agent'].queryset = CustomUser.objects.filter(user_type='delivery_agent')
        self.fields['delivery_agent'].empty_label = "Unassigned"

        
class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'name',
            'description',
            'base_price',
            'duration_days',
            'meal_types_included',
            'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'meal_types_included': forms.CheckboxSelectMultiple(),  # IMPORTANT ()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['meal_types_included'].queryset = MealType.objects.all()
        self.fields['meal_types_included'].help_text = ''


class DummyPaymentForm(forms.Form):
    PAYMENT_CHOICES = [
        ('card', 'Credit/Debit Card'),
        ('upi', 'UPI'),
    ]
    payment_method = forms.ChoiceField(choices=PAYMENT_CHOICES, widget=forms.RadioSelect, initial='card')
    card_number = forms.CharField(label="Card Number", max_length=16, required=False)
    card_expiry = forms.CharField(label="Expiry (MM/YY)", max_length=5, required=False)
    card_cvc = forms.CharField(label="CVC", max_length=3, required=False)
    upi_id = forms.CharField(label="UPI ID", max_length=50, required=False)