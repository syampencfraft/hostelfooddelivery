from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
from food_delivery.models import Subscription, Order, CustomUser, MealPlan

class Command(BaseCommand):
    help = 'Generates daily orders for active and paid subscriptions.'

    def handle(self, *args, **kwargs):
        today = date.today()
        self.stdout.write(self.style.SUCCESS(f'Starting daily order generation for {today}...'))

        active_subscriptions = Subscription.objects.filter(
            status='active',
            is_paid=True,
            start_date__lte=today,
            end_date__gte=today
        )

        generated_count = 0
        for sub in active_subscriptions:
            order_exists = Order.objects.filter(
                user=sub.user,
                meal_plan=sub.meal_plan,
                order_date=today
            ).exists()

            if not order_exists:

                Order.objects.create(
                    user=sub.user,
                    meal_plan=sub.meal_plan,
                    order_date=today,
                    status='pending',
                )
                generated_count += 1
                self.stdout.write(self.style.SUCCESS(f'Generated order for {sub.user.username} - {sub.meal_plan.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Order already exists for {sub.user.username} - {sub.meal_plan.name} on {today}'))


        self.stdout.write(self.style.SUCCESS(f'Finished. Generated {generated_count} new orders.'))