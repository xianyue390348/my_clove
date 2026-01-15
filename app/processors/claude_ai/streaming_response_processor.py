from typing import AsyncIterator, List
from loguru import logger

from fastapi.responses import StreamingResponse

from app.processors.base import BaseProcessor
from app.processors.claude_ai.context import ClaudeAIContext
from app.services.event_processing.event_serializer import EventSerializer
from app.models.streaming import StreamingEvent, ErrorEvent, ContentBlockDeltaEvent
from app.core.exceptions import ClaudeStreamingError


class StreamingResponseProcessor(BaseProcessor):
    """Processor that serializes event streams and creates a StreamingResponse."""

    def __init__(self):
        super().__init__()
        self.serializer = EventSerializer()

    async def process(self, context: ClaudeAIContext) -> ClaudeAIContext:
        """
        Serialize the event_stream and create a StreamingResponse.

        Before creating the response, we validate that the stream is stable by
        buffering events until we see actual content. If an error occurs during
        this buffer phase, we raise an exception (returns 429) so the client
        can retry, rather than returning 200 with an error event.

        Requires:
            - event_stream in context

        Produces:
            - response in context

        This processor typically marks the end of the pipeline by returning STOP action.
        """
        if context.response:
            logger.debug("Skipping StreamingResponseProcessor due to existing response")
            return context

        if not context.event_stream:
            logger.warning(
                "Skipping StreamingResponseProcessor due to missing event_stream"
            )
            return context

        if (
            not context.messages_api_request
            or context.messages_api_request.stream is not True
        ):
            logger.debug(
                "Skipping StreamingResponseProcessor due to non-streaming request"
            )
            return context

        logger.info("Creating streaming response from event stream")

        # Create a validated stream that buffers until content starts flowing
        validated_stream = ValidatedEventStream(context.event_stream)
        
        # Wait for stream to be validated (first content received)
        # This will raise ClaudeStreamingError if stream fails early
        await validated_stream.validate()

        # Now create the streaming response with the validated stream
        sse_stream = self.serializer.serialize_stream(validated_stream)

        context.response = StreamingResponse(
            sse_stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

        return context


class ValidatedEventStream:
    """
    A stream wrapper that validates the stream is stable before yielding events.
    
    It buffers events until we see actual content (content_block_delta),
    which indicates the model has started generating and the connection is stable.
    
    If an error occurs during the buffer phase, it raises an exception
    so the caller can return a proper HTTP error (429) instead of 200+error.
    """

    def __init__(self, event_stream: AsyncIterator[StreamingEvent]):
        self.event_stream = event_stream
        self.buffer: List[StreamingEvent] = []
        self.validated = False
        self.exhausted = False

    async def validate(self) -> None:
        """
        Buffer events until we see content flowing, then mark as validated.
        
        Raises:
            ClaudeStreamingError: If an error event is received before content starts
        """
        async for event in self.event_stream:
            self.buffer.append(event)

            # Check for error events during buffer phase
            if isinstance(event.root, ErrorEvent):
                error_type = event.root.error.type
                error_message = event.root.error.message
                logger.warning(
                    f"Stream error during validation: {error_type} - {error_message}"
                )
                # Raise exception so route returns 429 instead of 200
                raise ClaudeStreamingError(
                    error_type=error_type,
                    error_message=error_message,
                )

            # Check if we've seen actual content - stream is now stable
            if isinstance(event.root, ContentBlockDeltaEvent):
                logger.debug(
                    f"Stream validated after {len(self.buffer)} events"
                )
                self.validated = True
                return

        # Stream ended without content - still mark as validated
        # (could be an empty response, let it through)
        self.validated = True
        self.exhausted = True

    def __aiter__(self):
        """Return self as the async iterator."""
        return self

    async def __anext__(self) -> StreamingEvent:
        """Yield buffered events first, then continue with the stream."""
        if not self.validated:
            raise RuntimeError("Stream must be validated before iterating")

        # First, yield from buffer
        if self.buffer:
            return self.buffer.pop(0)

        # If stream was exhausted during validation, we're done
        if self.exhausted:
            raise StopAsyncIteration

        # Continue with remaining events from original stream
        try:
            return await self.event_stream.__anext__()
        except StopAsyncIteration:
            raise
