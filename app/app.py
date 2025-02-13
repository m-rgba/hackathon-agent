from agent import  gen_streaming_response, gen_thread_title
from django.db import models
from django.http import StreamingHttpResponse
from django.shortcuts import render
from ksuid import Ksuid
from nanodjango import Django
from openai import OpenAI
from logger import logger
import json
import os
import weave


app = Django(
    # ALLOWED_HOSTS=["localhost", "127.0.0.1"],
    # SECRET_KEY=os.environ["SECRET_KEY"],
    DEBUG=True
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


@app.api.post("/settings")
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

        # Handle optional settings
        optional_fields = {
            "api_model": "api_model",
            "weave_key": "weave_key",
            "weave_project": "weave_project",
            "github_token": "github_token",
            "figma_token": "figma_token"
        }

        for field_name, setting_key in optional_fields.items():
            if field_name in data:
                Settings.objects.update_or_create(
                    key=setting_key, defaults={"value": data[field_name]}
                )
        if weave_key and weave_project:
            weave_key = Settings.objects.get(key="weave_key").value
            weave_project = Settings.objects.get(key="weave_project").value
            if weave_key and weave_project:
                os.environ["WANDB_API_KEY"] = weave_key
                weave.init(weave_project)

        return {"message": "Settings updated successfully"}
    except json.JSONDecodeError:
        return {"error": "Invalid JSON payload"}
    except Exception as e:
        return {"error": "Failed to update settings"}

@app.api.get("/settings")
def get_settings(request):
    try:
        # Define settings to retrieve
        setting_keys = ["api_endpoint", "api_key", "api_model", "weave_key", "weave_project", "github_token", "figma_token"]
        settings_data = {}

        # Retrieve each setting
        for key in setting_keys:
            try:
                setting = Settings.objects.get(key=key)
                # Obscure sensitive information
                if key in ["api_key", "weave_key", "github_token", "figma_token"]:
                    settings_data[key] = "obfuscated"
                else:
                    settings_data[key] = setting.value
            except Settings.DoesNotExist:
                settings_data[key] = None

        return settings_data

    except Exception as e:
        return {"error": f"Failed to retrieve settings: {str(e)}"}

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

        # Create thread with optional thread_name
        thread = Thread.objects.create(
            thread_name=data.get("thread_name", "Untitled Thread"),
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
        threads = (
            Thread.objects.annotate(
                latest_message_date=models.Max('messages__created_on')
            )
            .order_by('-latest_message_date', '-created_on')
        )
        thread_list = []

        for thread in threads:
            thread_data = {
                "id": thread.id,
                "thread_name": thread.thread_name,
                "created_on": thread.created_on,
                "latest_message": thread.latest_message_date,
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


@app.api.post("/message/create")
def create_message(request):
    try:
        data = json.loads(request.body)

        # Validate required fields
        required_fields = ["thread_id", "sender", "type", "message"]
        if not all(field in data for field in required_fields):
            return {"error": "Missing required fields: 'thread_id', 'sender', 'type', or 'message'."}

        # Get thread
        try:
            thread = Thread.objects.get(id=data["thread_id"])
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}

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

@app.api.post("/message/send")
def send_message(request):
    try:
        data = json.loads(request.body)
        logger.info("Processing new message request")

        # Validate required fields
        required_fields = ["thread_id", "sender", "type", "message"]
        if not all(field in data for field in required_fields):
            logger.error("Missing required fields in request")
            return {"error": "Missing required fields: 'thread_id', 'sender', 'type', or 'message'."}

        # Get OpenAI settings
        try:
            api_endpoint = Settings.objects.get(key="api_endpoint").value
            api_key = Settings.objects.get(key="api_key").value
            api_model = Settings.objects.get(key="api_model").value
            logger.debug("Retrieved OpenAI settings")
        except Settings.DoesNotExist:
            logger.error("OpenAI settings not configured")
            return {"error": "OpenAI settings not configured"}

        # Get optional tokens
        try:
            figma_token = Settings.objects.get(key="figma_token").value
            logger.debug("Retrieved Figma token")
        except Settings.DoesNotExist:
            logger.debug("No Figma token configured")
            figma_token = None

        try:
            github_token = Settings.objects.get(key="github_token").value
            logger.debug("Retrieved GitHub token")
        except Settings.DoesNotExist:
            logger.debug("No GitHub token configured")
            github_token = None

        # Get thread
        try:
            thread = Thread.objects.get(id=data["thread_id"])
            logger.debug(f"Retrieved thread: {thread.id}")
        except Thread.DoesNotExist:
            logger.error(f"Thread not found: {data['thread_id']}")
            return {"error": "Thread not found"}

        # Generate title if thread is empty
        if thread.messages.count() == 0:
            logger.info("Generating title for new thread")
            title = gen_thread_title(
                api_endpoint=api_endpoint,
                api_key=api_key,
                api_model=api_model,
                message=data["message"]
            )
            thread.thread_name = title
            thread.save()
            logger.debug(f"Set thread title: {title}")

        # Create user message
        user_message = Message.objects.create(
            thread=thread,
            sender=data["sender"],
            type=data["type"],
            message=data["message"],
            metadata=data.get("metadata", {}),
        )
        logger.info(f"Created user message: {user_message.id}")

        # Create assistant message placeholder
        assistant_message = Message.objects.create(
            thread=thread,
            sender="Assistant",
            type="assistant",
            message="",
            metadata={},
        )
        logger.info(f"Created assistant message placeholder: {assistant_message.id}")

        # Get thread messages for context
        thread_messages = [
            {
                "sender": msg.sender,
                "message": msg.message,
                "type": msg.type
            }
            for msg in thread.messages.all().order_by('created_on')
        ]
        logger.debug(f"Retrieved {len(thread_messages)} messages for context")

        def generate_response():
            accumulated_message = ""
            try:
                # Generate streaming response
                logger.info("Starting streaming response generation")
                for content in gen_streaming_response(
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                    api_model=api_model,
                    message=data["message"],
                    thread_messages=thread_messages,
                    figma_token=figma_token,
                    github_token=github_token
                ):
                    accumulated_message += content
                    yield content.encode('utf-8')

                logger.info(f"Finished streaming. Final message length: {len(accumulated_message)}")
                # Update the assistant message with complete response
                assistant_message.message = accumulated_message
                assistant_message.save()
                logger.info("Saved assistant message")

            except Exception as e:
                error_message = f"\nError occurred: {str(e)}"
                logger.error(f"Error in generate_response: {str(e)}")
                # In case of error, update the message with error info
                assistant_message.message = f"Error: {str(e)}"
                assistant_message.metadata["error"] = str(e)
                assistant_message.save()
                yield error_message.encode('utf-8')

        logger.info("Returning streaming response")
        return StreamingHttpResponse(
            generate_response(),
            content_type='text/event-stream'
        )

    except Exception as e:
        logger.error(f"Failed to process message: {str(e)}")
        return {"error": f"Failed to process message: {str(e)}"}

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
