from abc import ABC, abstractmethod

import json
import argparse
import sys
import os
import re
from typing import List, Dict, Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

class LlmReleaseNotesGenerator:

    def __init__(self, changelog_exists: bool = False, prompt: str = None, aws_region: str = 'us-east-1'):
        self.aws_region = 'us-east-1'
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.max_tokens_override = 8000

        try:
            self.bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        except NoCredentialsError:
            print("Error: AWS credentials not found. Please configure your AWS credentials.")
            print("You can use: aws configure, environment variables, or IAM roles.")
            sys.exit(1)

    def call_bedrock_claude(self, prompt: str) -> str:
        """Call AWS Bedrock Claude Sonnet 3.5 v2 model"""

        # Estimate token count (rough approximation: 1 token ≈ 4 characters)
        estimated_tokens = len(prompt) // 4

        # Adjust max_tokens based on input size
        if self.max_tokens_override:
            max_tokens = self.max_tokens_override
        elif estimated_tokens > 50000:  # Very large input
            max_tokens = 8000
        elif estimated_tokens > 20000:  # Large input
            max_tokens = 6000
        elif estimated_tokens > 10000:  # Medium input
            max_tokens = 5000
        else:  # Small input
            max_tokens = 4000

        print(f"Estimated input tokens: ~{estimated_tokens:,}")
        print(f"Max output tokens set to: {max_tokens:,}")

        # Prepare the request body
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10000,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        try:
            # Call Bedrock
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json"
            )

            # Parse response
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"AWS Bedrock Error ({error_code}): {error_message}")

            if error_code == "AccessDeniedException":
                print("Make sure you have proper IAM permissions for Bedrock and the model is enabled in your region.")
            elif error_code == "ValidationException":
                print("Check if the Claude Sonnet 3.5 v2 model is available in your region.")
            elif error_code == "ThrottlingException":
                print("Request was throttled. Try again in a moment.")

            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error calling Bedrock: {e}")
            sys.exit(1)

    def generate_release_notes(self, prompt: str, output_file='') -> str:
        # Generate release notes using Claude
        print("Generating release notes using AWS Bedrock Claude Sonnet 3.5 v2...")
        release_notes = self.call_bedrock_claude(prompt)

        # Save to file if specified
        if output_file:
            try:
                # Create directory if it doesn't exist
                output_dir = os.path.dirname(output_file)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(release_notes)

                print(f"Release notes written to: {output_file}")
                print(f"File size: {os.path.getsize(output_file)} bytes")

            except Exception as e:
                print(f"Error writing to file {output_file}: {e}")
                print("Printing to console instead:")

        return release_notes
