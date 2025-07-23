# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
import json
import logging
import os
from typing import List

from pytablewriter import MarkdownTableWriter

from git.git_repository import GitRepository
from git.github_client import GitHubCommitsFetcher
from llms.llm_release_notes_generator import LlmReleaseNotesGenerator
from llms.prompts import COMMIT_PROMPT
from manifests.input_manifest import InputComponentFromSource, InputManifest, InputComponent
from release_notes_workflow.release_notes_component import ReleaseNotesComponents
from system.temporary_directory import TemporaryDirectory


class ReleaseNotes:

    def __init__(self, input_manifests: List[InputManifest], date: str, action_type: str) -> None:
        self.manifests = input_manifests  # type: ignore[assignment]
        self.date = date
        self.action_type = action_type
        self.filter_commits = ['flaky-test', 'testing']
        self.token = os.getenv('GITHUB_TOKEN')

    def table(self) -> MarkdownTableWriter:
        table_result = []
        for manifest in self.manifests:
            for component in manifest.components.select():
                if (component.name == 'OpenSearch' or component.name == 'OpenSearch-Dashboards' or component.name == 'notifications-core') and self.action_type == 'compile':
                    continue
                if hasattr(component, "repository"):
                    table_result.append(self.check(component, manifest.build.version, manifest.build.qualifier))  # type: ignore[arg-type]

        # Sort table_result based on Repo column
        table_result.sort(key=lambda x: (x[0], x[1]) if len(x) > 1 else x[0])

        if self.action_type == "check":
            headers = ["Repo", "Branch", "CommitID", "Commit Date", "Release Notes Exists"]
        elif self.action_type == "compile":
            headers = ["Repo", "Branch", "CommitID", "Commit Date", "Release Notes Exists", "URL"]
        else:
            raise ValueError("Invalid action_type. Use 'check' or 'compile'.")

        writer = MarkdownTableWriter(
            table_name=f"Core Components CommitID(after {self.date}) & Release Notes info",
            headers=headers,
            value_matrix=table_result
        )
        return writer

    def check(self, component: InputComponentFromSource, build_version: str, build_qualifier: str) -> List:
        results = []
        with TemporaryDirectory(chdir=True) as work_dir:
            results.append(component.name)
            results.append(f"[{component.ref}]")
            with GitRepository(
                    component.repository,
                    component.ref,
                    os.path.join(work_dir.name, component.name),
                    component.working_directory,
            ) as repo:
                logging.debug(f"Checked out {component.name} into {repo.dir}")
                release_notes = ReleaseNotesComponents.from_component(component, build_version, build_qualifier, repo.dir)
                commits = repo.log(self.date)
                if len(commits) > 0:
                    last_commit = commits[-1]
                    results.append(last_commit.id)
                    results.append(last_commit.date)
                else:
                    results.append(None)
                    results.append(None)
                results.append(release_notes.exists())

                if(release_notes.exists()):
                    releasenote = os.path.basename(release_notes.full_path)
                    repo_name = component.repository.split("/")[-1].split('.')[0]
                    repo_ref = component.ref.split("/")[-1]
                    url = f"https://raw.githubusercontent.com/opensearch-project/{repo_name}/{repo_ref}/release-notes/{releasenote}"
                    results.append(url)
                else:
                    results.append(None)
        return results

    def generate(self, product: str, component: InputComponentFromSource, build_version: str, build_qualifier: str, manifest_path: str = None) -> None:
        """Generate AI-powered release notes for a component."""
        with TemporaryDirectory(chdir=True) as work_dir:
            baseline_date = self.date
            with GitRepository(
                    component.repository,
                    component.ref,
                    os.path.join(work_dir.name, component.name),
                    component.working_directory, # Fetch full history to get all commits
            ) as repo:
                release_notes = ReleaseNotesComponents.from_component(component, build_version, build_qualifier, repo.dir)
                changelog_exist = os.path.isfile(os.path.join(repo.dir, 'CHANGELOG.md'))
                if changelog_exist:
                    pass
                else:
                    logging.warning(f"CHANGELOG.md not found in {repo.dir}. Using git log for commit history.")
                    github_commits = GitHubCommitsFetcher(self.date, component, self.token)
                    commits = github_commits.get_commit_details()

        #print(len(commits))
                    final_commits = [doc for doc in commits if not set(doc['Labels']) & set(self.filter_commits)]
                    commits_text = ""
                    for i, commit in enumerate(final_commits, 1):
                        message = commit.get("Message", "")
                        labels = commit.get("Labels", [])
                        pr_subject = commit.get("PullRequestSubject", "")

                        commits_text += f"{i}. PR Subject: {pr_subject}\n"
                        commits_text += f"   Message: {message}\n"
                        commits_text += f"   Labels: {', '.join(labels) if labels else 'None'}\n\n"
                    #print(json.dumps(final_commits, indent=2))
                    prompt = COMMIT_PROMPT.format(
                        plugin_name=component.name,
                        version=build_version,
                        repository_url=component.repository,
                        commits_text=commits_text
                    )
                    #print(f"DEBUG: Generated prompt for {component.name}:\n{prompt}")
                    llm_generator = LlmReleaseNotesGenerator()
                release_notes_raw = llm_generator.generate_release_notes(prompt)
        print(f"current working dir is {os.getcwd()}")
        with open(os.path.join(os.getcwd(), 'release-notes', f"opensearch-{component.name}{release_notes.filename}"), 'w') as f:
            f.write(release_notes_raw)
