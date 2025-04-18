# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

import unittest
from unittest.mock import Mock, patch

from sign_workflow.signer_jar import SignerJar
from sign_workflow.signer_mac import SignerMac
from sign_workflow.signer_pgp import SignerPGP
from sign_workflow.signer_windows import SignerWindows
from sign_workflow.signers import Signers


class TestSigners(unittest.TestCase):

    @patch("sign_workflow.signer.GitRepository")
    def test_signer_PGP(self, mock_repo: Mock) -> None:
        signer = Signers.create("linux", True, "release@opensearch.org")
        self.assertIs(type(signer), SignerPGP)

    @patch("sign_workflow.signer.GitRepository")
    def test_signer_windows(self, mock_repo: Mock) -> None:
        signer = Signers.create("windows", True, "release@opensearch.org")
        self.assertIs(type(signer), SignerWindows)

    @patch("sign_workflow.signer.GitRepository")
    def test_signer_macos(self, mock_repo: Mock) -> None:
        signer = Signers.create("mac", True, "release@opensearch.org")
        self.assertIs(type(signer), SignerMac)

    @patch("sign_workflow.signer.GitRepository")
    def test_signer_jar(self, mock_repo: Mock) -> None:
        signer = Signers.create("jar_signer", True, "release@opensearch.org")
        self.assertIs(type(signer), SignerJar)

    def test_signer_invalid(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            Signers.create("java", False, "release@opensearch.org")
        self.assertEqual(str(ctx.exception), "Unsupported type of platform for signing: java")
