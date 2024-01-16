import aws_cdk as core
import aws_cdk.assertions as assertions

from streaming_bot_websockets.streaming_bot_websockets_stack import StreamingBotWebsocketsStack

# example tests. To run these tests, uncomment this file along with the example
# resource in streaming_bot_websockets/streaming_bot_websockets_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = StreamingBotWebsocketsStack(app, "streaming-bot-websockets")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
