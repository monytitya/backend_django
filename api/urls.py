from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # ── Categories ───────────────────────────────────────────────
    path('categories/', views.CategoryListView.as_view(), name='api-categories'),

    # ── Products ─────────────────────────────────────────────────
    path('products/', views.ProductListView.as_view(), name='api-products'),
    path('products/search/', views.ProductSearchView.as_view(), name='api-product-search'),
    path('products/<slug:category_slug>/<slug:product_slug>/', views.ProductDetailView.as_view(), name='api-product-detail'),

    # ── Auth ─────────────────────────────────────────────────────
    path('auth/register/', views.RegisterView.as_view(), name='api-register'),
    path('auth/login/', views.LoginView.as_view(), name='api-login'),
    path('auth/logout/', views.LogoutView.as_view(), name='api-logout'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='api-token-refresh'),

    # ── Profile ──────────────────────────────────────────────────
    path('profile/', views.ProfileView.as_view(), name='api-profile'),
    path('profile/change-password/', views.ChangePasswordView.as_view(), name='api-change-password'),

    # ── Cart ─────────────────────────────────────────────────────
    path('cart/', views.CartView.as_view(), name='api-cart'),
    path('cart/add/', views.AddToCartView.as_view(), name='api-cart-add'),
    path('cart/remove/', views.RemoveFromCartView.as_view(), name='api-cart-remove'),

    # ── Orders ───────────────────────────────────────────────────
    path('orders/', views.OrderListView.as_view(), name='api-orders'),
    path('orders/place/', views.PlaceOrderView.as_view(), name='api-place-order'),
    path('orders/confirm-payment/', views.ConfirmPaymentView.as_view(), name='api-confirm-payment'),
    path('orders/<str:order_number>/', views.OrderDetailView.as_view(), name='api-order-detail'),

    # ── Reviews ──────────────────────────────────────────────────
    path('reviews/<int:product_id>/', views.SubmitReviewView.as_view(), name='api-submit-review'),
]

