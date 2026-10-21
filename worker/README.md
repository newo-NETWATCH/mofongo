# Worker

The photo tagger that runs on EC2: polls the SQS queue, tags each photo with CLIP, writes the tags to DynamoDB.
