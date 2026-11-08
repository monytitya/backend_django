from rest_framework import serializers
from category.models import Category
from store.models import Product, Variation, ReviewRating, ProductGallery
from accounts.models import Account, UserProfile
from carts.models import Cart, CartItem
from orders.models import Order, Payment, OrderProduct


# ─── Category ────────────────────────────────────────────────────────────────

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'category_name', 'slug', 'description', 'cat_image']


# ─── Product ─────────────────────────────────────────────────────────────────

class VariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variation
        fields = ['id', 'variation_category', 'variation_value', 'is_active']


class ProductGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductGallery
        fields = ['id', 'image']


class ReviewRatingSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ReviewRating
        fields = ['id', 'user_name', 'subject', 'review', 'rating', 'created_at', 'updated_at']

    def get_user_name(self, obj):
        return obj.user.full_name()


class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    average_review = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'product_name', 'slug', 'description', 'price',
            'images', 'stock', 'is_available', 'category',
            'average_review', 'review_count', 'created_date',
        ]

    def get_average_review(self, obj):
        return obj.averageReview()

    def get_review_count(self, obj):
        return obj.countReview()


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    variations = VariationSerializer(many=True, read_only=True, source='variation_set')
    gallery = ProductGallerySerializer(many=True, read_only=True, source='productgallery_set')
    reviews = serializers.SerializerMethodField()
    average_review = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'product_name', 'slug', 'description', 'price',
            'images', 'stock', 'is_available', 'category',
            'variations', 'gallery', 'reviews',
            'average_review', 'review_count',
            'created_date', 'modified_date',
        ]

    def get_reviews(self, obj):
        reviews = ReviewRating.objects.filter(product=obj, status=True)
        return ReviewRatingSerializer(reviews, many=True).data

    def get_average_review(self, obj):
        return obj.averageReview()

    def get_review_count(self, obj):
        return obj.countReview()


# ─── Account / Auth ──────────────────────────────────────────────────────────

class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, min_length=6)

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        if Account.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError({'email': 'Email is already registered.'})
        return data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['address_line_1', 'address_line_2', 'city', 'state', 'country', 'profile_picture']


class AccountSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(source='userprofile', read_only=True)

    class Meta:
        model = Account
        fields = ['id', 'first_name', 'last_name', 'username', 'email', 'phone_number', 'date_joined', 'profile']


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, min_length=6)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return data


# ─── Cart ────────────────────────────────────────────────────────────────────

class CartItemVariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variation
        fields = ['id', 'variation_category', 'variation_value']


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    variations = CartItemVariationSerializer(many=True, read_only=True)
    sub_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'variations', 'quantity', 'sub_total', 'is_active']

    def get_sub_total(self, obj):
        return obj.sub_total()


class CartSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True)
    total = serializers.FloatField()
    tax = serializers.FloatField()
    grand_total = serializers.FloatField()
    item_count = serializers.IntegerField()


class AddToCartSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variations = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text='List of Variation IDs to add (e.g. color, size)'
    )


class RemoveCartItemSerializer(serializers.Serializer):
    cart_item_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    remove_all = serializers.BooleanField(
        default=False,
        help_text='If true, remove the entire line. If false, decrease qty by 1.'
    )


# ─── Orders ──────────────────────────────────────────────────────────────────

class PlaceOrderSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)
    phone = serializers.CharField(max_length=15)
    email = serializers.EmailField()
    address_line_1 = serializers.CharField(max_length=50)
    address_line_2 = serializers.CharField(max_length=50, required=False, allow_blank=True)
    country = serializers.CharField(max_length=50)
    state = serializers.CharField(max_length=50)
    city = serializers.CharField(max_length=50)
    order_note = serializers.CharField(max_length=100, required=False, allow_blank=True)


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'payment_id', 'payment_method', 'amount_paid', 'status', 'created_at']


class OrderProductSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    variations = CartItemVariationSerializer(many=True, read_only=True)

    class Meta:
        model = OrderProduct
        fields = ['id', 'product', 'variations', 'quantity', 'product_price', 'ordered']


class OrderSerializer(serializers.ModelSerializer):
    payment = PaymentSerializer(read_only=True)
    order_products = OrderProductSerializer(many=True, read_only=True, source='orderproduct_set')

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'first_name', 'last_name', 'phone', 'email',
            'address_line_1', 'address_line_2', 'country', 'state', 'city',
            'order_note', 'order_total', 'tax', 'status', 'is_ordered',
            'payment', 'order_products', 'created_at', 'updated_at',
        ]


class ConfirmPaymentSerializer(serializers.Serializer):
    order_number = serializers.CharField()
    transaction_id = serializers.CharField(help_text='PayPal / payment gateway transaction ID')
    payment_method = serializers.CharField(default='PayPal')
    status = serializers.CharField(default='COMPLETED')


class SubmitReviewSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=100)
    review = serializers.CharField(max_length=500)
    rating = serializers.FloatField(min_value=1, max_value=5)

