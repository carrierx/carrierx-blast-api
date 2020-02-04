from rest_framework import serializers

from .models import Message


class RecordingSerializer(serializers.Serializer):
    created = serializers.DateTimeField(read_only=True)
    length = serializers.IntegerField(source='duration', read_only=True)
    url = serializers.CharField(read_only=True)


class RecipientCallSerializer(serializers.Serializer):

    def to_representation(self, instance):
        """Convert Call instance into simple string"""
        return instance.to_number


class MessageSerializer(serializers.Serializer):
    # TODO: Use serializers in post methods
    # Expose views on API/doc

    id = serializers.IntegerField(read_only=True)
    created = serializers.DateTimeField(read_only=True)
    caller = serializers.CharField(required=False, allow_blank=True, read_only=True, max_length=11)
    status = serializers.CharField(required=False, allow_blank=True, max_length=100)
    title = serializers.CharField(required=False, allow_blank=True, max_length=100)
    schedule = serializers.DateTimeField(required=False)
    userdata = serializers.CharField(source='user_data', required=False, allow_blank=True, max_length=100)
    recipients = RecipientCallSerializer(source="call_set", required=False, many=True)
    voc = RecordingSerializer(source='recording', required=False)
    recipients_requested_dnc = serializers.BooleanField(required=True)

    def create(self, validated_data):
        """
        Create and return a new `Message` instance, given the validated data.
        """

        instance = Message.objects.create()
        instance.status = validated_data.get('status', instance.status)
        instance.title = validated_data.get('title', instance.title)
        instance.schedule = validated_data.get('schedule', instance.schedule)
        instance.user_data = validated_data.get('userdata', instance.user_data)

        return instance

    def update(self, instance, validated_data):
        """
        Update and return an existing `Message` instance, given the validated data.
        """

        instance.status = validated_data.get('status', instance.status)
        instance.title = validated_data.get('title', instance.title)
        instance.schedule = validated_data.get('schedule', instance.schedule)
        instance.user_data = validated_data.get('userdata', instance.user_data)
        instance.save()
        return instance


class CallSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    started = serializers.DateTimeField(read_only=True)
    finished = serializers.DateTimeField(read_only=True)
    shout_id = serializers.IntegerField(source='message.pk', read_only=True)
    phone = serializers.CharField(source='to_number', read_only=True)
    status = serializers.CharField(required=False, allow_blank=True, max_length=100, read_only=True)
    Q850 = serializers.IntegerField(required=False, read_only=True)


class DNCNumberSerializer(serializers.Serializer):
    number = serializers.CharField()
