# food_delivery/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),

    # Resident URLs
    path('subscriptions/plans/', views.subscription_plans_view, name='subscription_plans'),
    path('subscribe/<int:plan_id>/', views.subscribe_to_plan_view, name='subscribe_to_plan'),
    path('order/daily/', views.resident_daily_order_select, name='resident_daily_order_select'),
    path('order/daily/<int:meal_type_id>/<str:order_date_str>/', views.resident_daily_order_select, name='resident_daily_order_select_with_date_meal'),

    # Vendor URLs
    path('vendor/menu-items/', views.vendor_menu_item_list, name='vendor_menu_item_list'),
    path('vendor/menu-items/add/', views.vendor_menu_item_create, name='vendor_menu_item_create'),
    path('vendor/menu-items/<int:pk>/edit/', views.vendor_menu_item_update, name='vendor_menu_item_update'),
    path('vendor/daily-menu/', views.vendor_daily_menu_create_update, name='vendor_daily_menu_create_update'),
    # path('vendor/daily-menu/<str:menu_date_str>/<int:meal_type_id>/', views.vendor_daily_menu_create_update, name='vendor_daily_menu_create_update_specific'),
    path('vendor/orders/<int:order_id>/update/',
    views.vendor_update_order_status,
    name='vendor_update_order_status'),
     path(
        'vendor/orders/',
        views.vendor_orders_list,
        name='vendor_orders_list'
    ),

    # path('vendor/daily-order/<int:order_id>/update-status/', views.vendor_update_daily_order_status, name='vendor_update_daily_order_status'),
    path('vendor/my-subscriptions/', views.vendor_manage_subscriptions, name='vendor_manage_subscriptions'),
    path('vendor/menu-items/', views.vendor_menu_item_list, name='vendor_menu_item_list'),

    # Delivery Agent URLs
    path('delivery-agent/daily-order/<int:order_id>/update-status/', views.delivery_agent_update_daily_order_status, name='delivery_agent_update_daily_order_status'),

    # Admin URLs
    path('admin-daily-orders/pending/', views.admin_pending_daily_orders_view, name='admin_pending_daily_orders'),
    path('admin-daily-order/<int:order_id>/assign-agent/', views.admin_assign_delivery_agent_to_daily_order, name='admin_assign_delivery_agent_to_daily_order'),
    path('site-admin/dashboard/', views.custom_admin_dashboard, name='custom_admin_dashboard'),
    path('site-admin/users/', views.custom_admin_manage_users, name='custom_admin_manage_users'),
    path('site-admin/plans/', views.custom_admin_manage_plans, name='custom_admin_manage_plans'),
    path('site-admin/plans/create/', views.custom_admin_plan_create, name='custom_admin_plan_create'),
    path('site-admin/plans/<int:pk>/update/', views.custom_admin_plan_update, name='custom_admin_plan_update'),
    
    # We can keep the existing admin-related URLs or move them under the new prefix
    path('site-admin/daily-orders/pending/', views.admin_pending_daily_orders_view, name='admin_pending_daily_orders'),
    path('site-admin/daily-order/<int:order_id>/assign-agent/', views.admin_assign_delivery_agent_to_daily_order, name='admin_assign_delivery_agent_to_daily_order'),

    path('subscribe/start/<int:plan_id>/', views.subscribe_to_plan_view, name='subscribe_to_plan'),
    path('payment/', views.payment_page, name='payment_page'),
    path('payment/process/', views.process_payment, name='process_payment'),




path(
    'site-admin/meal-types/',
    views.admin_meal_type_list_create,
    name='admin_meal_type'
),



    path(
        'delivery/orders/',
        views.delivery_agent_orders,
        name='delivery_agent_orders'
    ),

    path(
        'delivery/order/<int:order_id>/accept/',
        views.delivery_accept_order,
        name='delivery_accept_order'
    ),

    path(
        'delivery/order/<int:order_id>/reject/',
        views.delivery_reject_order,
        name='delivery_reject_order'
    ),

    path(
        'delivery/order/<int:order_id>/complete/',
        views.delivery_complete_order,
        name='delivery_complete_order'
    ),



path(
    'resident/order/<int:order_id>/track/',
    views.resident_live_delivery_tracking,
    name='resident_live_tracking'
),

path(
    'resident/delivery-history/',
    views.resident_delivery_history,
    name='resident_delivery_history'
),

path(
    'delivery/history/',
    views.delivery_agent_history,
    name='delivery_agent_history'
),
path(
    'resident/order/<int:order_id>/track/',
    views.resident_live_delivery_tracking,
    name='resident_live_tracking'
),


]