#!/usr/bin/env python3
import os

import aws_cdk as cdk

from streaming_bot_websockets.streaming_bot_websockets_stack import StreamingBotWebsocketsStack
from streaming_bot_websockets.chatbot_frontend_stack import ChatbotFrontendStack
from streaming_bot_websockets.config.config_parser import get_config

#Get the customer name, for naming the stack
config = get_config()
app = cdk.App()
StreamingBotWebsocketsStack(app, f"StreamingBotWebsocketsStack-{config['deployment']['name']}")
ChatbotFrontendStack(app,f"ChatbotFrontEndStack-{config['deployment']['name']}")

app.synth()
