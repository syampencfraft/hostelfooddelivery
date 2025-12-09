from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, SubscriptionPlan, VendorSubscription, VendorMenuItem, DailyMenu, UserSubscription, DailyOrder, DailyOrderItem, Payment, MealType

# Custom User Admin

# Register all models
admin.site.register(MealType)
admin.site.register(CustomUser)
admin.site.register(SubscriptionPlan, )
admin.site.register(VendorSubscription, )
admin.site.register(VendorMenuItem, )
admin.site.register(DailyMenu, )
admin.site.register(UserSubscription, )
admin.site.register(DailyOrder, )
admin.site.register(DailyOrderItem, )
admin.site.register(Payment, )