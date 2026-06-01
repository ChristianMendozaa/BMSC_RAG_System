"""
Multimodal chat handler for Gemma-4 E4B (vision) under llama-cpp-python.

llama-cpp-python's `clip_model_path` shorthand on `Llama()` does NOT set up a
multimodal handler — in 0.3.x `Llama.__init__` doesn't even accept that kwarg,
so it is silently absorbed by **kwargs and ignored. The chat handler stays a
text-only Jinja2 formatter, the mmproj projector is never loaded, and images are
dropped: Gemma answers as if no image was provided.

The fix is to pass `chat_handler=` explicitly, built from a `Llava15ChatHandler`
subclass that (a) loads the mmproj vision projector via `clip_model_path` and
(b) renders the prompt with Gemma's own turn-marker chat template so the image
URL is replaced by the mtmd media marker before tokenization.
"""

# Gemma-4 uses <|turn>user / <|turn>model turn markers and <|turn>system for
# system prompts (confirmed from GGUF tokenizer.chat_template metadata).
# The image URL in the rendered text is replaced by the mtmd media marker
# before tokenization, so the model receives actual vision embeddings.
_GEMMA4_CHAT_FORMAT = (
    # No {{ bos_token }} here — Llava15ChatHandler sets add_special=True which
    # adds BOS automatically; including it in the template would double it.
    "{% for message in messages %}"
    "{% if message['role'] == 'user' %}"
    "<|turn>user\n"
    "{% if message['content'] is iterable and message['content'] is not string %}"
    "{% for content in message['content'] %}"
    # image_url: render the URL as text; Llava15ChatHandler replaces it with
    # the mtmd media marker before tokenization, injecting visual embeddings.
    "{% if content['type'] == 'image_url' %}"
    "{% if content.image_url is string %}{{ content.image_url }}\n"
    "{% else %}{{ content.image_url.url }}\n{% endif %}"
    "{% elif content['type'] == 'text' %}{{ content['text'] | trim }}"
    "{% endif %}"
    "{% endfor %}"
    "{% else %}{{ message['content'] | trim }}{% endif %}"
    "<turn|>\n"
    "{% elif message['role'] in ('assistant', 'model') %}"
    "<|turn>model\n{{ message['content'] | trim }}<turn|>\n"
    "{% elif message['role'] == 'system' %}"
    "<|turn>system\n{{ message['content'] | trim }}<turn|>\n"
    "{% endif %}"
    "{% endfor %}"
    "{% if add_generation_prompt %}<|turn>model\n{% endif %}"
)


def make_gemma4_handler() -> type:
    """Return a Llava15ChatHandler subclass wired with Gemma-4's chat template.

    Instantiate it with `clip_model_path=<mmproj>` and pass the instance to
    `Llama(chat_handler=...)` to enable real multimodal captioning.
    """
    from llama_cpp.llama_chat_format import Llava15ChatHandler

    class Gemma4ChatHandler(Llava15ChatHandler):
        CHAT_FORMAT = _GEMMA4_CHAT_FORMAT
        DEFAULT_SYSTEM_MESSAGE = None

    return Gemma4ChatHandler
