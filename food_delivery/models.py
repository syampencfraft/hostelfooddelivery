from django.db import models
from django.contrib.auth.models import AbstractUser
from datetime import date
from decimal import Decimal

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ("admin", "Admin"),
        ("resident", "Resident"),
        ("vendor", "Vendor"),
        ("delivery_agent", "Delivery Agent"),
        ("warden", "Warden"),
    )
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default="resident")
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_approved = models.BooleanField(default=False, help_text="Designates whether this user has been approved by an admin or warden.")
    warden = models.ForeignKey('self', null=True, blank=True, limit_choices_to={'user_type': 'warden'}, on_delete=models.SET_NULL, related_name='residents', help_text="The warden responsible for this resident.")

    def __str__(self):
        return self.username

class MealType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name
    
    
class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    duration_days = models.IntegerField(
        help_text="Duration of the plan in days (e.g., 30 for a monthly plan)"
    )
    meal_types_included = models.ManyToManyField(MealType, help_text="Meal types covered by this plan")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class VendorSubscription(models.Model):
    """Which subscription plans a vendor wants to serve"""
    vendor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'user_type': 'vendor'})
    # make nullable/blank to avoid migration prompt for existing rows
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('vendor', 'subscription_plan')

    def __str__(self):
        return f"{self.vendor.username} serves {self.subscription_plan.name}"

class VendorMenuItem(models.Model):
    ITEM_MEAL_TYPE_CHOICES = (
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("snacks", "Snacks"),
        ("dinner", "Dinner"),
    )
    vendor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'user_type': 'vendor'}, related_name='menu_items')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    meal_type = models.CharField(max_length=20, choices=ITEM_MEAL_TYPE_CHOICES)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    is_available_globally = models.BooleanField(default=True, help_text="Is this item generally available from the vendor?")
    subscription_plans = models.ManyToManyField(
        SubscriptionPlan,
        help_text="Which subscription plans is this item available for?",
        related_name='menu_items'
    )

    def __str__(self):
        return f"{self.name} by {self.vendor.username} ({self.meal_type})"


class UserSubscription(models.Model):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("paused", "Paused"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    )
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'user_type': 'resident'}, related_name='user_subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    # allow nullable/default to avoid migration prompt
    start_date = models.DateField(null=True, blank=True, default=date.today)
    end_date = models.DateField(null=True, blank=True, default=date.today)
    total_amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    is_paid = models.BooleanField(default=False)
    subscribed_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s {self.plan.name} subscription ({self.status})"

class DailyMenu(models.Model):
    vendor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'user_type': 'vendor'}, related_name='daily_menus')
    menu_date = models.DateField(default=date.today)
    meal_type = models.ForeignKey(MealType, on_delete=models.CASCADE)
    available_items = models.ManyToManyField(VendorMenuItem, help_text="Items available on this menu")

    class Meta:
        unique_together = ('vendor', 'menu_date', 'meal_type')
        ordering = ['menu_date', 'meal_type']

    def __str__(self):
        return f"{self.vendor.username}'s {self.meal_type.name} Menu for {self.menu_date}"

class DailyOrder(models.Model):
    ORDER_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("submitted", "Submitted"),
        ("prepared", "Prepared"),
        ("out_for_delivery", "Out for Delivery"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    )
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'user_type': 'resident'}, related_name='daily_orders')
    # allow nullable so existing orders don't break when adding this FK later
    user_subscription = models.ForeignKey(UserSubscription, on_delete=models.CASCADE, related_name='daily_orders_from_subscription', null=True, blank=True)
    order_date = models.DateField(default=date.today)
    meal_type = models.ForeignKey(MealType, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default="submitted")
    delivery_agent = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                       limit_choices_to={'user_type': 'delivery_agent'},
                                       related_name='assigned_daily_orders')
    assigned_time = models.DateTimeField(null=True, blank=True)
    delivered_time = models.DateTimeField(null=True, blank=True)
    ordered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'order_date', 'meal_type')
        ordering = ['-order_date', 'meal_type']

    def __str__(self):
        return f"{self.user.username}'s {self.meal_type.name} Order for {self.order_date}"

    @property
    def total_order_cost(self):
        return sum(item.quantity * item.price_at_order_time for item in self.items.all())


class DailyOrderItem(models.Model):
    daily_order = models.ForeignKey(DailyOrder, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(VendorMenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    # provide default to avoid migration prompt
    price_at_order_time = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('daily_order', 'menu_item')

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} for Order {self.daily_order.id}"


class Payment(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payments')
    user_subscription = models.ForeignKey(UserSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_for_subscription')
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    payment_date = models.DateTimeField(auto_now_add=True)
    is_successful = models.BooleanField(default=False)

    def __str__(self):
        return f"Payment of {self.amount} by {self.user.username}"


class BulkOrder(models.Model):
    ORDER_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("submitted", "Submitted"),
        ("prepared", "Prepared"),
        ("out_for_delivery", "Out for Delivery"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    )
    warden = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'user_type': 'warden'}, related_name='bulk_orders')
    order_date = models.DateField(default=date.today)
    meal_type = models.ForeignKey(MealType, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default="submitted")
    delivery_agent = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
                                       limit_choices_to={'user_type': 'delivery_agent'},
                                       related_name='assigned_bulk_orders')
    assigned_time = models.DateTimeField(null=True, blank=True)
    delivered_time = models.DateTimeField(null=True, blank=True)
    ordered_at = models.DateTimeField(auto_now_add=True)
    
    # Bulk order specifics
    special_requirements = models.TextField(blank=True, help_text="Any special instructions for the bulk order")
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['-order_date', 'meal_type']

    def __str__(self):
        return f"Bulk Order by {self.warden.username} for {self.meal_type.name} on {self.order_date}"
    
class BulkOrderItem(models.Model):
    bulk_order = models.ForeignKey(BulkOrder, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(VendorMenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price_at_order_time = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('bulk_order', 'menu_item')

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} for Bulk Order {self.bulk_order.id}"

