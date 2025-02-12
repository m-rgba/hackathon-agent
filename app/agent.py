from asgiref.sync import sync_to_async
from django.db import models
from django.shortcuts import render
from ksuid import Ksuid
from nanodjango import Django
from openai import OpenAI
import asyncio
import json

app = Django(
    # ALLOWED_HOSTS=["localhost", "127.0.0.1"],
    # SECRET_KEY=os.environ["SECRET_KEY"],
    # DEBUG=False,
)

### Models


class KSUIDField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 27  # Base62 KSUID length
        kwargs["unique"] = True
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        if add and not getattr(model_instance, self.attname):
            # Generate new KSUID and convert to string
            value = str(Ksuid())
            setattr(model_instance, self.attname, value)
            return value
        return super().pre_save(model_instance, add)


class Settings(models.Model):
    key = models.CharField(max_length=255)
    value = models.TextField()


class Thread(models.Model):
    id = KSUIDField(primary_key=True)
    thread_name = models.CharField(max_length=255)
    created_on = models.DateTimeField(auto_now_add=True)
    edited_on = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)


class Message(models.Model):
    id = KSUIDField(primary_key=True)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=255)
    type = models.CharField(max_length=100)
    message = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)
    edited_on = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)


### API


@app.api.post("/settings/openai")
def update_openai_settings(request):
    try:
        data = json.loads(request.body)

        # Validate required fields
        required_fields = ["api_endpoint", "api_key"]
        if not all(field in data for field in required_fields):
            return {"error": "Missing required fields"}

        # Update or create settings
        Settings.objects.update_or_create(
            key="api_endpoint", defaults={"value": data["api_endpoint"]}
        )

        Settings.objects.update_or_create(
            key="api_key", defaults={"value": data["api_key"]}
        )

        # Handle optional api_model setting
        if "api_model" in data:
            Settings.objects.update_or_create(
                key="api_model", defaults={"value": data["api_model"]}
            )

        return {"message": "Settings updated successfully"}
    except json.JSONDecodeError:
        return {"error": "Invalid JSON payload"}
    except Exception as e:
        return {"error": "Failed to update settings"}


@app.api.get("/settings/openai/models")
def get_openai_models(request):
    try:
        # Get settings
        api_endpoint = Settings.objects.get(key="api_endpoint").value
        api_key = Settings.objects.get(key="api_key").value
    except Settings.DoesNotExist:
        return {"error": "OpenAI API endpoint and key must be configured first"}

    try:
        # Initialize OpenAI client
        client = OpenAI(base_url=api_endpoint, api_key=api_key)

        # Fetch models
        models = client.models.list()
        return {"models": [model.id for model in models]}

    except Exception as e:
        return {"error": f"Failed to fetch models from OpenAI API: {str(e)}"}


@app.api.post("/thread/create")
def create_thread(request):
    try:
        data = json.loads(request.body)

        # Create thread
        thread = Thread.objects.create(
            thread_name=data["thread_name"],
            metadata=data.get("metadata", {}),
        )

        return {
            "message": "Thread created successfully",
            "thread": {
                "id": thread.id,
                "thread_name": thread.thread_name,
                "created_on": thread.created_on,
            },
        }

    except Exception as e:
        return {"error": f"Failed to create thread: {str(e)}"}


@app.api.get("/threads")
def list_threads(request):
    try:
        threads = Thread.objects.all()
        thread_list = []

        for thread in threads:
            thread_data = {
                "id": thread.id,
                "thread_name": thread.thread_name,
                "created_on": thread.created_on,
                "metadata": thread.metadata,
            }
            thread_list.append(thread_data)

        return {"threads": thread_list}

    except Exception as e:
        return {"error": f"Failed to list threads: {str(e)}"}


@app.api.get("/thread/{thread_id}")
def get_thread(request, thread_id: str):
    try:
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}
        
        thread_data = {
            "id": thread.id,
            "thread_name": thread.thread_name,
            "created_on": thread.created_on,
            "edited_on": thread.edited_on,
            "metadata": thread.metadata,
            "messages": [
                {
                    "id": message.id,
                    "sender": message.sender,
                    "type": message.type,
                    "message": message.message,
                    "created_on": message.created_on,
                }
                for message in thread.messages.all()
            ],
        }

        return thread_data

    except Exception as e:
        return {"error": f"Failed to get thread details: {str(e)}"}


@app.api.put("/thread/{thread_id}")
def update_thread(request, thread_id: str):
    try:
        data = json.loads(request.body)

        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}

        if "thread_name" in data:
            thread.thread_name = data["thread_name"]

        if "metadata" in data:
            thread.metadata.update(data["metadata"])

        thread.save()

        return {
            "message": "Thread updated successfully",
            "thread": {
                "id": thread.id,
                "thread_name": thread.thread_name,
                "metadata": thread.metadata,
            },
        }

    except Exception as e:
        return {"error": f"Failed to update thread: {str(e)}"}


@app.api.delete("/thread/{thread_id}")
def delete_thread(request, thread_id: str):
    try:
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}

        thread.delete()
        return {"message": "Thread deleted successfully"}

    except Exception as e:
        return {"error": f"Failed to delete thread: {str(e)}"}


@app.api.post("/thread/{thread_id}/message/create")
def create_message(request, thread_id: str):
    try:
        data = json.loads(request.body)

        # Get thread
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}

        # Validate required fields
        required_fields = ["sender", "type", "message"]
        if not all(field in data for field in required_fields):
            return {"error": "Missing required fields: 'sender', 'type', or 'message'."}

        # Create message
        message = Message.objects.create(
            thread=thread,
            sender=data["sender"],
            type=data["type"],
            message=data["message"],
            metadata=data.get("metadata", {}),
        )

        return {
            "message": "Message created successfully",
            "message_data": {
                "id": message.id,
                "sender": message.sender,
                "type": message.type,
                "message": message.message,
                "created_on": message.created_on,
                "metadata": message.metadata,
            },
        }

    except Exception as e:
        return {"error": f"Failed to create message: {str(e)}"}


@app.api.put("/message/{message_id}")
def update_message(request, message_id: str):
    try:
        data = json.loads(request.body)

        # Get message
        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return {"error": "Message not found"}

        # Update fields if provided
        if "sender" in data:
            message.sender = data["sender"]
        if "type" in data:
            message.type = data["type"]
        if "message" in data:
            message.message = data["message"]
        if "metadata" in data:
            message.metadata.update(data["metadata"])

        message.save()

        return {
            "message": "Message updated successfully",
            "message_data": {
                "id": message.id,
                "sender": message.sender,
                "type": message.type,
                "message": message.message,
                "created_on": message.created_on,
                "edited_on": message.edited_on,
                "metadata": message.metadata,
            },
        }

    except Exception as e:
        return {"error": f"Failed to update message: {str(e)}"}


@app.api.delete("/message/{message_id}")
def delete_message(request, message_id: str):
    try:
        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return {"error": "Message not found"}

        message.delete()
        return {"message": "Message deleted successfully"}

    except Exception as e:
        return {"error": f"Failed to delete message: {str(e)}"}


### Routes


@app.route("/")
def index(request):
    return render(request, "index.html")
