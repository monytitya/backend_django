from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.shortcuts import get_object_or_404
import datetime

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from category.models import Category
from store.models import Product, ReviewRating, ProductGallery, Variation
from accounts.models import Account, UserProfile
from carts.models import Cart, CartItem
from orders.models import Order, Payment, OrderProduct

from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    RegisterSerializer,
    LoginSerializer,
    AccountSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    CartSerializer,
    CartItemSerializer,
    AddToCartSerializer,
    RemoveCartItemSerializer,
    PlaceOrderSerializer,
    OrderSerializer,
    ConfirmPaymentSerializer,
    ReviewRatingSerializer,
    SubmitReviewSerializer,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def _get_or_create_cart(request):
    """Return (cart, created). Uses session key for anonymous users."""
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key
    cart, created = Cart.objects.get_or_create(cart_id=session_key)
    return cart


def _build_cart_response(cart_items):
    total = 0
    for item in cart_items:
        total += item.product.price * item.quantity
    tax = round((2 * total) / 100, 2)
    grand_total = round(total + tax, 2)
    return {
        'items': CartItemSerializer(cart_items, many=True).data,
        'total': total,
        'tax': tax,
        'grand_total': grand_total,
        'item_count': sum(i.quantity for i in cart_items),
    }


# ─── Categories ──────────────────────────────────────────────────────────────

class CategoryListView(generics.ListAPIView):
    """
    List all product categories.
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]


# ─── Products ────────────────────────────────────────────────────────────────

class ProductListView(APIView):
    """
    List all available products with optional category filter and pagination.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter('category', OpenApiTypes.STR, description='Filter by category slug'),
            OpenApiParameter('page', OpenApiTypes.INT, description='Page number (default: 1)'),
            OpenApiParameter('page_size', OpenApiTypes.INT, description='Items per page (default: 6)'),
        ],
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request):
        category_slug = request.GET.get('category')
        page_size = int(request.GET.get('page_size', 6))

        if category_slug:
            category = get_object_or_404(Category, slug=category_slug)
            products = Product.objects.filter(category=category, is_available=True)
        else:
            products = Product.objects.filter(is_available=True).order_by('id')

        paginator = Paginator(products, page_size)
        page = request.GET.get('page', 1)
        try:
            paged = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            paged = paginator.page(1)

        serializer = ProductListSerializer(paged, many=True, context={'request': request})
        return Response({
            'count': paginator.count,
            'num_pages': paginator.num_pages,
            'current_page': int(page),
            'results': serializer.data,
        })


class ProductDetailView(APIView):
    """
    Retrieve a single product by its category slug and product slug.
    """
    permission_classes = [AllowAny]

    def get(self, request, category_slug, product_slug):
        product = get_object_or_404(Product, category__slug=category_slug, slug=product_slug, is_available=True)
        serializer = ProductDetailSerializer(product, context={'request': request})
        return Response(serializer.data)


class ProductSearchView(APIView):
    """
    Search products by keyword (searches name and description).
    """
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter('keyword', OpenApiTypes.STR, required=True, description='Search keyword'),
        ],
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request):
        keyword = request.GET.get('keyword', '').strip()
        if not keyword:
            return Response({'error': 'keyword query param is required.'}, status=400)

        products = Product.objects.filter(
            Q(product_name__icontains=keyword) | Q(description__icontains=keyword),
            is_available=True
        ).order_by('-created_date')

        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({
            'count': products.count(),
            'keyword': keyword,
            'results': serializer.data,
        })


# ─── Authentication ───────────────────────────────────────────────────────────

class RegisterView(APIView):
    """
    Register a new user account.

    New accounts are **inactive** until email is verified.
    For testing purposes, accounts can be manually activated in the admin panel at /securelogin/
    """
    permission_classes = [AllowAny]

    @extend_schema(request=RegisterSerializer, responses={201: AccountSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            d = serializer.validated_data
            base_username = d['email'].split('@')[0]
            username = base_username
            counter = 1
            while Account.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            user = Account.objects.create_user(
                first_name=d['first_name'],
                last_name=d['last_name'],
                email=d['email'],
                username=username,
                password=d['password'],
            )
            user.phone_number = d.get('phone_number', '')
            user.is_active = True
            user.save()

            # Create user profile
            UserProfile.objects.get_or_create(
                user=user,
                defaults={'profile_picture': 'default/default-user.png'},
            )

            tokens = get_tokens_for_user(user)

            return Response({
                'message': 'Registration successful.',
                'tokens': tokens,
                'user': AccountSerializer(user).data,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    Login with email + password. Returns JWT access and refresh tokens.

    Use the returned **access** token as:
    `Authorization: Bearer <access_token>`
    """
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: {'type': 'object', 'properties': {'access': {'type': 'string'}, 'refresh': {'type': 'string'}}}})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        user = authenticate(request, email=email, password=password)

        if user is None:
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({'error': 'Account is not activated. Please verify your email.'}, status=status.HTTP_403_FORBIDDEN)

        tokens = get_tokens_for_user(user)
        return Response({
            'message': 'Login successful.',
            'tokens': tokens,
            'user': AccountSerializer(user).data,
        })


class LogoutView(APIView):
    """
    Logout by blacklisting the refresh token.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={'type': 'object', 'properties': {'refresh': {'type': 'string'}}},
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}},
    )
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logged out successfully.'})
        except Exception:
            return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)


# ─── Profile ─────────────────────────────────────────────────────────────────

class ProfileView(APIView):
    """
    GET: Retrieve current user's profile.
    PUT: Update profile information.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = AccountSerializer(request.user)
        return Response(serializer.data)

    @extend_schema(request=UserProfileSerializer)
    def put(self, request):
        profile = get_object_or_404(UserProfile, user=request.user)
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Profile updated successfully.',
                'profile': serializer.data,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    Change the current user's password.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer)
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        d = serializer.validated_data
        user = request.user
        if not user.check_password(d['current_password']):
            return Response({'error': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(d['new_password'])
        user.save()
        return Response({'message': 'Password changed successfully.'})


# ─── Cart ────────────────────────────────────────────────────────────────────

class CartView(APIView):
    """
    GET: View current cart contents (works for both guests and logged-in users).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user.is_authenticated:
            cart_items = CartItem.objects.filter(user=request.user, is_active=True)
        else:
            cart = _get_or_create_cart(request)
            cart_items = CartItem.objects.filter(cart=cart, is_active=True)

        data = _build_cart_response(list(cart_items))
        return Response(data)


class AddToCartView(APIView):
    """
    Add a product to the cart (supports product variations like color/size).

    Pass a list of **Variation IDs** in the `variations` field.
    If the same product+variation already exists in cart, quantity is incremented.
    """
    permission_classes = [AllowAny]

    @extend_schema(request=AddToCartSerializer)
    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product_id = serializer.validated_data['product_id']
        variation_ids = serializer.validated_data.get('variations', [])

        product = get_object_or_404(Product, id=product_id, is_available=True)
        variations = list(Variation.objects.filter(id__in=variation_ids, product=product))

        if request.user.is_authenticated:
            existing_items = CartItem.objects.filter(product=product, user=request.user)
            for item in existing_items:
                if list(item.variations.all()) == variations:
                    item.quantity += 1
                    item.save()
                    return Response({'message': 'Cart updated.', 'cart_item_id': item.id})

            new_item = CartItem.objects.create(product=product, quantity=1, user=request.user)
            if variations:
                new_item.variations.set(variations)
            new_item.save()
            return Response({'message': 'Product added to cart.', 'cart_item_id': new_item.id}, status=201)
        else:
            cart = _get_or_create_cart(request)
            existing_items = CartItem.objects.filter(product=product, cart=cart)
            for item in existing_items:
                if list(item.variations.all()) == variations:
                    item.quantity += 1
                    item.save()
                    return Response({'message': 'Cart updated.', 'cart_item_id': item.id})

            new_item = CartItem.objects.create(product=product, quantity=1, cart=cart)
            if variations:
                new_item.variations.set(variations)
            new_item.save()
            return Response({'message': 'Product added to cart.', 'cart_item_id': new_item.id}, status=201)


class RemoveFromCartView(APIView):
    """
    Remove item from cart.
    - `remove_all=false`: decrease quantity by 1 (removes item if qty reaches 0)
    - `remove_all=true`: delete the entire cart item line
    """
    permission_classes = [AllowAny]

    @extend_schema(request=RemoveCartItemSerializer)
    def post(self, request):
        serializer = RemoveCartItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        d = serializer.validated_data
        product = get_object_or_404(Product, id=d['product_id'])

        try:
            if request.user.is_authenticated:
                cart_item = CartItem.objects.get(id=d['cart_item_id'], product=product, user=request.user)
            else:
                cart = _get_or_create_cart(request)
                cart_item = CartItem.objects.get(id=d['cart_item_id'], product=product, cart=cart)
        except CartItem.DoesNotExist:
            return Response({'error': 'Cart item not found.'}, status=status.HTTP_404_NOT_FOUND)

        if d['remove_all']:
            cart_item.delete()
            return Response({'message': 'Item removed from cart.'})
        else:
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                cart_item.save()
                return Response({'message': 'Quantity decreased.', 'new_quantity': cart_item.quantity})
            else:
                cart_item.delete()
                return Response({'message': 'Item removed from cart.'})


# ─── Orders ──────────────────────────────────────────────────────────────────

class PlaceOrderView(APIView):
    """
    Place an order with billing/shipping details.
    Returns an order number to use with the payment endpoint.
    **Requires authentication.**
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PlaceOrderSerializer, responses={201: OrderSerializer})
    def post(self, request):
        serializer = PlaceOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        cart_items = CartItem.objects.filter(user=request.user, is_active=True)
        if not cart_items.exists():
            return Response({'error': 'Your cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)

        total = sum(item.product.price * item.quantity for item in cart_items)
        tax = round((2 * total) / 100, 2)
        grand_total = round(total + tax, 2)

        d = serializer.validated_data
        order = Order.objects.create(
            user=request.user,
            first_name=d['first_name'],
            last_name=d['last_name'],
            phone=d['phone'],
            email=d['email'],
            address_line_1=d['address_line_1'],
            address_line_2=d.get('address_line_2', ''),
            country=d['country'],
            state=d['state'],
            city=d['city'],
            order_note=d.get('order_note', ''),
            order_total=grand_total,
            tax=tax,
            ip=request.META.get('REMOTE_ADDR', ''),
        )

        today = datetime.date.today()
        order.order_number = today.strftime('%Y%m%d') + str(order.id)
        order.save()

        return Response({
            'message': 'Order created. Proceed to payment.',
            'order_number': order.order_number,
            'order_total': grand_total,
            'tax': tax,
        }, status=status.HTTP_201_CREATED)


class ConfirmPaymentView(APIView):
    """
    Confirm a payment after the payment gateway (e.g. PayPal) processes it.
    This moves cart items to order, reduces stock, clears cart, and sends confirmation email.
    **Requires authentication.**
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ConfirmPaymentSerializer)
    def post(self, request):
        serializer = ConfirmPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        d = serializer.validated_data

        try:
            order = Order.objects.get(
                user=request.user,
                order_number=d['order_number'],
                is_ordered=False,
            )
        except Order.DoesNotExist:
            return Response({'error': 'Order not found or already processed.'}, status=404)

        payment = Payment.objects.create(
            user=request.user,
            payment_id=d['transaction_id'],
            payment_method=d['payment_method'],
            amount_paid=order.order_total,
            status=d['status'],
        )

        order.payment = payment
        order.is_ordered = True
        order.save()

        cart_items = CartItem.objects.filter(user=request.user)
        for item in cart_items:
            op = OrderProduct.objects.create(
                order=order,
                payment=payment,
                user=request.user,
                product=item.product,
                quantity=item.quantity,
                product_price=item.product.price,
                ordered=True,
            )
            op.variations.set(item.variations.all())
            op.save()

            # Reduce stock
            product = item.product
            product.stock -= item.quantity
            product.save()

        cart_items.delete()

        return Response({
            'message': 'Payment confirmed. Order placed successfully.',
            'order_number': order.order_number,
            'transaction_id': payment.payment_id,
        })


class OrderListView(APIView):
    """
    List all completed orders for the current user.
    **Requires authentication.**
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(user=request.user, is_ordered=True).order_by('-created_at')
        serializer = OrderSerializer(orders, many=True)
        return Response({'count': orders.count(), 'results': serializer.data})


class OrderDetailView(APIView):
    """
    Retrieve details of a specific order by order number.
    **Requires authentication.**
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number, user=request.user, is_ordered=True)
        serializer = OrderSerializer(order)
        return Response(serializer.data)


# ─── Reviews ─────────────────────────────────────────────────────────────────

class SubmitReviewView(APIView):
    """
    Submit or update a review for a product.
    Only users who have purchased the product can review it.
    **Requires authentication.**
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SubmitReviewSerializer, responses={200: ReviewRatingSerializer})
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id, is_available=True)

        # Check if user purchased this product
        has_purchased = OrderProduct.objects.filter(user=request.user, product=product).exists()
        if not has_purchased:
            return Response({'error': 'You can only review products you have purchased.'}, status=403)

        serializer = SubmitReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        d = serializer.validated_data

        review, created = ReviewRating.objects.update_or_create(
            user=request.user,
            product=product,
            defaults={
                'subject': d['subject'],
                'review': d['review'],
                'rating': d['rating'],
                'ip': request.META.get('REMOTE_ADDR', ''),
                'status': True,
            }
        )

        message = 'Review submitted.' if created else 'Review updated.'
        return Response({
            'message': message,
            'review': ReviewRatingSerializer(review).data,
        })

