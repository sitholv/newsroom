"""Safe API representations with explicit editorial validation."""

from rest_framework import serializers

from .models import Article, Newsletter, Publisher, User


class UserSerializer(serializers.ModelSerializer):
    """Expose public identity only, never hashes, tokens or email
    addresses."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "role"]
        read_only_fields = fields


class PublisherSerializer(serializers.ModelSerializer):
    """Represent a publisher and its editorial membership
    identifiers."""

    class Meta:
        model = Publisher
        fields = ["id", "name", "description", "editors", "journalists"]
        read_only_fields = fields


class ArticleSerializer(serializers.ModelSerializer):
    """Prevent owner/approval forgery and validate publisher
    membership."""

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "content",
            "author",
            "publisher",
            "created_at",
            "approved",
        ]
        read_only_fields = ["id", "author", "created_at", "approved"]

    def validate(self, attrs):
        """Require the article's actual journalist to belong to its
        publisher."""
        author = (
            self.instance.author
            if self.instance
            else self.context["request"].user
        )
        publisher = attrs.get(
            "publisher", self.instance.publisher if self.instance else None
        )
        if (
            publisher
            and not publisher.journalists.filter(pk=author.pk).exists()
        ):
            raise serializers.ValidationError(
                {
                    "publisher": "The author must belong to this publisher.",
                }
            )
        return attrs


class NewsletterSerializer(serializers.ModelSerializer):
    """Represent newsletter contents while rejecting hidden draft
    articles."""

    articles = serializers.PrimaryKeyRelatedField(
        queryset=Article.objects.filter(approved=True), many=True
    )

    def to_representation(self, instance):
        """Hide references to articles that returned to draft after
        editing."""
        result = super().to_representation(instance)
        result["articles"] = list(
            instance.articles.filter(approved=True).values_list(
                "pk", flat=True
            )
        )
        return result

    class Meta:
        model = Newsletter
        fields = [
            "id",
            "title",
            "description",
            "created_at",
            "author",
            "publisher",
            "articles",
        ]
        read_only_fields = ["id", "created_at", "author"]

    def validate(self, attrs):
        """Reject publisher assignments unrelated to the newsletter's
        author."""
        author = (
            self.instance.author
            if self.instance
            else self.context["request"].user
        )
        publisher = attrs.get(
            "publisher", self.instance.publisher if self.instance else None
        )
        if publisher:
            members = (
                publisher.editors
                if author.role == User.Role.EDITOR
                else publisher.journalists
            )
            if not members.filter(pk=author.pk).exists():
                raise serializers.ValidationError(
                    {
                        "publisher": "Author must belong to this publisher.",
                    }
                )
        return attrs
