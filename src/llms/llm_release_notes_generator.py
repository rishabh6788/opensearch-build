from abc import ABC, abstractmethod

from llms.llm_release_notes_generator_changelog import LlmReleaseNotesGeneratorChangelog
import json
import argparse
import sys
import os
import re
from typing import List, Dict, Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

class LlmReleaseNotesGenerator():

    def __init__(self, changelog_exists: bool = False, prompt: str = None, aws_region: str = 'us-east-1'):
        self.changelog_exists = changelog_exists
        self.aws_region = 'us-east-1'
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.max_tokens_override = 8000

        try:
            self.bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        except NoCredentialsError:
            print("Error: AWS credentials not found. Please configure your AWS credentials.")
            print("You can use: aws configure, environment variables, or IAM roles.")
            sys.exit(1)

    def load_commits_data(self, file_path: str) -> List[Dict]:
        """Load commits data from JSON file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle both direct list and grouped data
            if isinstance(data, dict):
                # If it's grouped data, flatten it
                commits = []
                for label, commit_list in data.items():
                    commits.extend(commit_list)
                return commits
            else:
                return data

        except FileNotFoundError:
            print(f"Error: File {file_path} not found.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {file_path}: {e}")
            sys.exit(1)

    def create_release_notes_prompt(self, commits_data: List[Dict], plugin_name: str,
                                    version: str, repository_url: str) -> str:
        """Create the prompt for Claude to generate release notes"""

        # Convert commits data to a clean format for the prompt
        commits_text = ""
        for i, commit in enumerate(commits_data, 1):
            message = commit.get("Message", "")
            labels = commit.get("Labels", [])
            pr_subject = commit.get("PullRequestSubject", "")

            commits_text += f"{i}. PR Subject: {pr_subject}\n"
            commits_text += f"   Message: {message}\n"
            commits_text += f"   Labels: {', '.join(labels) if labels else 'None'}\n\n"

        prompt = f"""I need you to generate OpenSearch plugin release notes from commit data. Please follow the OpenSearch release notes format exactly.

**Plugin Information:**
- Plugin Name: {plugin_name}
- Version: {version}
- Repository URL: {repository_url}

**Commit Data:**
{commits_text}

**Instructions:**

1. **Label-based Categorization Logic:**
   - First, check if any labels match these categories (case-insensitive, partial matches allowed):
     * "breaking change" or "breaking" → Breaking Changes
     * "feature" or "feat" → Features  
     * "enhancement" or "improve" → Enhancements
     * "bug" or "fix" or "bugfix" → Bug Fixes
     * "infrastructure" or "ci" or "test" → Infrastructure
     * "documentation" or "docs" → Documentation
     * "maintenance" or "version" or "support" → Maintenance
     * "refactor" or "refactoring" → Refactoring

2. **Fallback Message Analysis:**
   - If no labels match, analyze the Message content and PullRequestSubject to determine the appropriate category following below guidelines:
    * Features: A change that introduce a net new unit of functionality of a software system that satisfies a requirement, 
    represents a design decision, and provides a potential configuration option. As for improvement on existing features, 
    use the Enhancement category. As for fixes on existing features, use the Bug Fixes category. Example: "Add start/stop batch actions on detector list page"
    * Enhancements: A change that improves the performance, usability, or reliability of an existing feature without changing its core functionality. Example: "Improve detector list page performance"
    * Bug Fixes: A change that resolves an issue or defect in the software. Example: "Fix issue with detector creation form validation"
    * Infrastructure: A change that modifies the underlying architecture, build process, or deployment of the software Example: "Update CI/CD pipeline for better reliability"
    * Documentation: A change that updates or adds documentation, such as README files, user guides, or API docs. Example: "Update README with new installation instructions"
    * Maintenance: A change that involves routine upkeep, such as version updates, dependency management, or minor tweaks that do not fit other categories. Example: "Update dependencies to latest versions"
    * Refactoring: A change that improves the internal structure of the code without changing its external behavior. Example: "Refactor detector service for better readability or Make ClusterDetailsEventProcessor and all its access methods non-static"
   - Do not lose any commit information, even if it doesn't match any category

3. **Entry Format:**
   - Use PullRequestSubject as the main content for each entry
   - Extract PR number from PullRequestSubject (format: (#123))
   - Format: `* <description> ([#<number>]({repository_url}/pull/<number>))`
   - Always use asterisk (*) for bullet points
   - Always wrap PR links in parentheses

4. **Output Requirements:**
   - Generate markdown with ### headers for each category
   - Only include categories that have entries
   - Sort categories in this order: Breaking Changes, Features, Enhancements, Bug Fixes, Infrastructure, Documentation, Maintenance, Refactoring
   - Each entry should be a single line with proper PR link formatting

5. **PR Link Format:**
   - Extract PR number from PullRequestSubject
   - Format as: `([#<number>]({repository_url}/pull/<number>))`
   - Example: `([#456](https://github.com/opensearch-project/anomaly-detection/pull/456))`
   
6. **Important Notes:**
   - Every commit should be categorized into exactly one category
   - If you cannot determine the appropriate category from labels OR content analysis, place the entry in an "Unknown" category
   - Do not skip any commits - every entry must appear somewhere in the release notes
   - Prioritize Message over PullRequestSubject for determining category when using fallback analysis

Generate the release notes in proper OpenSearch format:"""

        return prompt

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

    def build_repository_url(self, repository: str) -> str:
        """Build GitHub repository URL from repository argument"""
        if repository.startswith("http"):
            return repository
        elif "/" in repository:
            return f"https://github.com/{repository}"
        else:
            return f"https://github.com/opensearch-project/{repository}"

    def extract_repo_info(self, repository_url: str) -> tuple:
        """Extract owner and repo name from repository URL"""
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repository_url)
        if match:
            owner, repo = match.groups()
            return owner, repo.replace('.git', '')
        return "opensearch-project", "unknown-plugin"

    def generate_release_notes(self, commits_file: str, repository: str,
                               version: str, output_file: str = None) -> str:
        """
        Generate release notes from commits file

        Args:
            commits_file: Path to JSON file with commits data
            repository: Repository identifier (formats: 'owner/repo', 'repo', or full URL)
            version: Version number for the release
            output_file: Output file path (optional)

        Returns:
            Generated release notes as string
        """

        # Load commits data
        print(f"Loading commits from {commits_file}...")
        commits_data = self.load_commits_data(commits_file)

        if not commits_data:
            print("No commits found in the input file.")
            return ""

        print(f"Found {len(commits_data)} commits to process.")

        # Build repository URL
        repository_url = self.build_repository_url(repository)
        owner, repo_name = self.extract_repo_info(repository_url)

        print(f"Repository URL: {repository_url}")
        print(f"Plugin name: {repo_name}")

        # Create prompt
        prompt = self.create_release_notes_prompt(commits_data, repo_name, version, repository_url)

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
