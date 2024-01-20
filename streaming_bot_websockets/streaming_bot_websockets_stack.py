from aws_cdk import (
    CfnParameter,
    RemovalPolicy,
    CfnOutput,
    Duration,
    Stack,
    aws_lambda as _lambda,
    aws_apigatewayv2_alpha as apigwv2,
    aws_iam as iam,
    aws_events as events,
    aws_dynamodb as dynamodb,
    aws_events_targets as targets,
    aws_s3 as s3,
    aws_s3_notifications as s3_notify,
    aws_cloudwatch as cloudwatch
)
from constructs import Construct
from aws_cdk.aws_apigatewayv2_integrations_alpha import WebSocketLambdaIntegration
from aws_cdk import aws_opensearchserverless as opensearchserverless
import json
from streaming_bot_websockets.config.config_parser import get_config

class StreamingBotWebsocketsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        config_data = get_config()
        
        EMBEDDING_MODEL_ID_DEFAULT='amazon.titan-embed-text-v1'
       
        embedding_model_aws_id = CfnParameter(self, "embeddingModelId", 
                                          type="String",
                                          default=EMBEDDING_MODEL_ID_DEFAULT,
                                          description="The AWS embedding model name.")
        
        events_table = create_dynamodb_table(self,scope=scope,table_name='events_table')

        '''Create a platform specific langchain layer - Linux'''
        boto3_lanchain_lyr = _lambda.LayerVersion(self,id="boto3-langchain-layer",\
                                                    code=_lambda.AssetCode("streaming_bot_websockets/layers/boto3_langchain/layer-boto3-langchain-libs.zip"),
                                                    compatible_architectures=[_lambda.Architecture.X86_64],
                                                    compatible_runtimes=[_lambda.Runtime.PYTHON_3_11])
                                                    
        
        '''An Eventbridge bus for custom events'''
        messaging_app_event_bus = events.EventBus(self, "MessagingAppEventBus",
            event_bus_name="MessagingAppEventBus"
        )
        '''Create a Web socket API Gateway'''
        web_socket_api = apigwv2.WebSocketApi(self, "1bzWebscoketDemoApi")
        web_socket_api_stage = apigwv2.WebSocketStage(self, "1bzWebscoketDemoApiStage",
            web_socket_api=web_socket_api,
            stage_name="dev",
            auto_deploy=True
        )

        lambda_ws_message_handler_role = iam.Role(self,"lambdaWsMsgHandlerRole", \
                                                           assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'))
        
    
    

        #service-role/ is required for the Managed policy, see the function docs for more info
        AWSLambdaBasicExecutionRole = iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
        lambda_ws_message_handler_role.add_managed_policy(AWSLambdaBasicExecutionRole)
        lambda_ws_message_handler_role.attach_inline_policy(iam.Policy(self, "bedrockInvokePolicyForWs",
            statements=[iam.PolicyStatement(
            actions=["bedrock:InvokeModel",
                     "bedrock:InvokeModelWithResponseStream"],
            resources=["*"]
        )]
        ))

        lambda_ws_message_handler_role.attach_inline_policy(iam.Policy(self, "apiGatewayWsPolicyForWs",
            statements=[iam.PolicyStatement(
            actions=["execute-api:Invoke",
                     "execute-api:ManageConnections"],
            resources=["*"]
        )]
        ))

        lambda_ws_message_handler_role.attach_inline_policy(iam.Policy(self, "openSearchPolicyForWs",
            statements=[iam.PolicyStatement(
            actions=["aoss:*","aoss:APIAccessAll"],
            resources=["*"]
        )]
        ))

        lambda_ws_message_handler_role.attach_inline_policy(iam.Policy(self, "eventsPutPolicyForLambda",
            statements=[iam.PolicyStatement(
            actions=["events:PutEvents"],
            resources=[messaging_app_event_bus.event_bus_arn]
        )]
        ))

        '''Web socket Message Handler'''
        lambda_ws_message_handler = _lambda.Function(
                self, 
                'ws_message_handler',
                role=lambda_ws_message_handler_role,
                runtime=_lambda.Runtime.PYTHON_3_11,
                code=_lambda.AssetCode('streaming_bot_websockets/lambdas/ws_message_handler'),
                timeout=Duration.seconds(600),
                layers=[boto3_lanchain_lyr],
                handler='app.lambda_handler')
        lambda_ws_message_handler.add_environment("WS_API_URL",(web_socket_api_stage.url).replace('wss','https'))
        

        lambda_billing_message_handler_role = iam.Role(self,"lambdaBillingHandlerRole", \
                                                           assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'))
        lambda_billing_message_handler_role.add_managed_policy(AWSLambdaBasicExecutionRole)

        '''#Create other handlers for Message analysis, billing etc. '''
        lambda_billing_message_handler = _lambda.Function(
            self, 
            'billing_message_handler',
            role=lambda_billing_message_handler_role,
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.AssetCode('streaming_bot_websockets/lambdas/billing_message_handler'),
            timeout=Duration.seconds(120),
            handler='app.lambda_handler')
        
        
        lambda_sentiment_analysis_message_handler_role = iam.Role(self,"lambdaSentimentHandlerRole", \
                                                           assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'))
        lambda_sentiment_analysis_message_handler_role.add_managed_policy(AWSLambdaBasicExecutionRole)
        lambda_sentiment_analysis_message_handler = _lambda.Function(
            self, 
            'sentiment_analysis_message_handler',
            role = lambda_sentiment_analysis_message_handler_role,
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.AssetCode('streaming_bot_websockets/lambdas/sentiment_analysis_message_handler'),
            timeout=Duration.seconds(120),
            layers=[boto3_lanchain_lyr],
            handler='app.lambda_handler')
        
        lambda_sentiment_analysis_message_handler_role.attach_inline_policy(iam.Policy(self, \
            "bedrockInvokePolicyForSentimentAnalysisHandler",
            statements=[iam.PolicyStatement(
            actions=["bedrock:InvokeModel",
                     "bedrock:InvokeModelWithResponseStream"],
            resources=["*"]
        )]
        ))
        
        billing_events_rule = events.Rule(self, "BillingMessagingApprule",
        event_pattern=events.EventPattern(
            source=["com.onebyzero.chatter.chat_message"]
        ),
        event_bus=messaging_app_event_bus
        )

        sentiment_analysis_events_rule = events.Rule(self, "AnalysisMessagingApprule",
        event_pattern=events.EventPattern(
            source=["com.onebyzero.chatter.chat_message"]
        ),
        event_bus=messaging_app_event_bus
        )

        # Add the Lambda function as a target for the rule
        #rule.add_target(targets.LambdaFunction())
        billing_events_rule.add_target(targets.LambdaFunction(lambda_billing_message_handler))
        sentiment_analysis_events_rule.add_target(targets.LambdaFunction(lambda_sentiment_analysis_message_handler))
    
        web_socket_api.add_route("$default",
            integration=WebSocketLambdaIntegration("SendMessageIntegration", lambda_ws_message_handler)
        )
        web_socket_api.add_route("$connect",
            integration=WebSocketLambdaIntegration("SendMessageIntegration", lambda_ws_message_handler)
        )
        web_socket_api.add_route("$disconnect",
            integration=WebSocketLambdaIntegration("SendMessageIntegration", lambda_ws_message_handler)
        )

       

        
        lambda_vector_db_ingestion_handler_role = iam.Role(self,"lambdaVectorDbIngestRole", \
                                                           assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'))
      

        bucket = s3.Bucket(self, "KnowledgeRepositoryRaw")
        

        lambda_vector_db_ingestion_handler_role.attach_inline_policy(iam.Policy(self, "bedrockInvokeEmbeddingPolicy",
            statements=[iam.PolicyStatement(
            actions=["bedrock:InvokeModel",
                     "bedrock:InvokeModelWithResponseStream"],
            resources=["*"]
        )]
        ))

        lambda_vector_db_ingestion_handler_role.attach_inline_policy(iam.Policy(self, "openSearchPolicy",
            statements=[iam.PolicyStatement(
            actions=["aoss:*","aoss:APIAccessAll"],
            resources=["*"]
        )]
        ))

        lambda_vector_db_ingestion_handler_role.attach_inline_policy(iam.Policy(self, "s3BucketObjectAccess",
            statements=[iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{bucket.bucket_arn}/*"]
        )]
        ))

        #service-role/ is required for the Managed policy, see the function docs for more info
        AWSLambdaBasicExecutionRole = iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
        lambda_vector_db_ingestion_handler_role.add_managed_policy(AWSLambdaBasicExecutionRole)
        lambda_vector_db_ingestion_handler = _lambda.Function(
                self, 
                'vector_db_ingestion_handler',
                runtime=_lambda.Runtime.PYTHON_3_11,
                role=lambda_vector_db_ingestion_handler_role,
                code=_lambda.AssetCode('streaming_bot_websockets/lambdas/vectordb_ingestion_handler'),
                timeout=Duration.seconds(900),
                layers=[boto3_lanchain_lyr],
                memory_size=2048,
                handler='app.lambda_handler')
        
        #Grant the vector db ingest function access to the S3 bucket
        bucket.grant_read(lambda_vector_db_ingestion_handler)

        notification = s3_notify.LambdaDestination(lambda_vector_db_ingestion_handler)
        notification.bind(self, bucket)

        # Add Create Event only for Object creation
        bucket.add_object_created_notification(
           notification)
        
        collection_name = f"vectorcoll-{config_data['deployment']['name']}".lower()
        vector_collection = opensearchserverless.CfnCollection(self,collection_name,
        name=collection_name,
        # the properties below are optional
        description="A vectorized collection of documents, your knowledge base",
        type="VECTORSEARCH"
        ) 
     
        encryption_policy = {"Rules":[{"ResourceType":"collection","Resource":[f"collection/{collection_name}"]}],"AWSOwnedKey":True}
        network_policy = [{"Rules":[{"ResourceType":"collection","Resource":[f"collection/{collection_name}"]}, {"ResourceType":"dashboard","Resource":["collection/product-collection"]}],"AllowFromPublic":True}]
        data_access_policy = [{
        "Rules": [
        {
            "ResourceType": "index",
            "Resource": [
            f"index/{collection_name}/*"
            ],
            "Permission": [
            "aoss:*"
            ]
        }
        ],
        "Principal": [lambda_vector_db_ingestion_handler_role.role_arn,lambda_ws_message_handler_role.role_arn]
        }]

           # Encryption policy is needed in order for the collection to be created
        encPolicy = opensearchserverless.CfnSecurityPolicy(self, f"secpolicy",
        name=f"SecPlcy{config_data['deployment']['name']}".lower(),
        policy=json.dumps(encryption_policy),
        type='encryption'
        )

        #Network policy is required so that the dashboard can be viewed!
        netPolicy = opensearchserverless.CfnSecurityPolicy(self, f"netpolicy", 
        name=f"NetPlcy{config_data['deployment']['name']}".lower(),
        policy=json.dumps(network_policy),
        type='network'
        )

        dataPolicy = opensearchserverless.CfnAccessPolicy(self, \
                                                          f"DataPlcy-{config_data['deployment']['name']}".lower(),\
                                                          name=f"DataPlcy{config_data['deployment']['name']}".lower(),
                    type='data',
                    policy=json.dumps(data_access_policy))


        #Stack fails without adding the dependency, as this is required to create the Collection
        vector_collection.add_dependency(encPolicy)
        vector_collection.add_dependency(netPolicy)
        vector_collection.add_dependency(dataPolicy)

        events_table.grant_read_write_data(lambda_billing_message_handler)
        events_table.grant_read_write_data(lambda_sentiment_analysis_message_handler)
        events_table.grant_read_write_data(lambda_vector_db_ingestion_handler)
        events_table.grant_read_write_data(lambda_ws_message_handler)

        lambda_billing_message_handler.add_environment("EVENTS_TABLE_NAME",events_table.table_name)
        lambda_sentiment_analysis_message_handler.add_environment("EVENTS_TABLE_NAME",events_table.table_name)
        lambda_ws_message_handler.add_environment("EVENTS_TABLE_NAME",events_table.table_name)
        lambda_vector_db_ingestion_handler.add_environment("EVENTS_TABLE_NAME",events_table.table_name)

        lambda_vector_db_ingestion_handler.add_environment("OPENSEARCH_EP",
                                                           vector_collection.attr_collection_endpoint)
        lambda_vector_db_ingestion_handler.add_environment("EMBEDDING_MODEL_ID",
                                                           embedding_model_aws_id.value_as_string)
        
        lambda_ws_message_handler.add_environment("LLM_STREAMING_ENABLED","NO")
        #TODO - Remove hardcoding, pass it as a CDK param, else default
        vector_db_index_name = "docs-index"
        lambda_vector_db_ingestion_handler.add_environment("DOCUMENTS_INDEX",
                                                           vector_db_index_name)
        lambda_ws_message_handler.add_environment("DOCUMENTS_INDEX",
                                                           vector_db_index_name)
        lambda_ws_message_handler.add_environment("OPENSEARCH_EP",
                                                           vector_collection.attr_collection_endpoint)
        
        lambda_ws_message_handler.add_environment("EVENT_BUS_NAME",messaging_app_event_bus.event_bus_name)

        # Create a CloudWatch Dashboard
        dashboard = cloudwatch.Dashboard(
            self, "MyChatterDashboard",
            dashboard_name=f"Chatter_Dashboard-{config_data['deployment']['name']}"
        )
       
       
       # print outputs
        CfnOutput(self, "OPENSEARCH_COLLECTION_EP", value=vector_collection.attr_collection_endpoint)
        CfnOutput(self, "OPENSEARCH_COLLECTION_NAME", value=vector_collection.name)
        CfnOutput(self, "VECTOR_DB_S3_DROPOFF_BUCKET_NAME", value=bucket.bucket_name)
        CfnOutput(self,"EVENTS_TABLE_NAME",value=events_table.table_name)
        CfnOutput(self,"EVENT_BUS_NAME",value=messaging_app_event_bus.event_bus_name)


def create_dynamodb_table(self,scope, \
                          table_name, \
                          primary_key_name="pk",sort_key_name="sk",\
                          removal_policy = RemovalPolicy.DESTROY):
    table = dynamodb.Table(self, table_name,
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, 
        partition_key=dynamodb.Attribute(name=primary_key_name, type=dynamodb.AttributeType.STRING), 
        sort_key=dynamodb.Attribute(name=sort_key_name, type=dynamodb.AttributeType.STRING),
        removal_policy=removal_policy)
    return table