from django.test import TestCase
from path import path
import shutil
import os
from github_sync import import_from_github, export_to_github
from git import Repo
from django.conf import settings
from xmodule.modulestore.django import modulestore
from xmodule.modulestore import Location
from override_settings import override_settings
from github_sync.exceptions import GithubSyncError


@override_settings(DATA_DIR=path('test_root'))
class GithubSyncTestCase(TestCase):

    def cleanup(self):
        shutil.rmtree(self.repo_dir, ignore_errors=True)
        shutil.rmtree(self.remote_dir, ignore_errors=True)

    def setUp(self):
        self.working_dir = path(settings.TEST_ROOT)
        self.repo_dir = self.working_dir / 'local_repo'
        self.remote_dir = self.working_dir / 'remote_repo'

        # make sure there's no stale data lying around
        self.cleanup()

        shutil.copytree('common/test/data/toy', self.remote_dir)

        remote = Repo.init(self.remote_dir)
        remote.git.add(A=True)
        remote.git.commit(m='Initial commit')
        remote.git.config("receive.denyCurrentBranch", "ignore")

        modulestore().collection.drop()

        self.import_revision, self.import_course = import_from_github({
            'path': self.repo_dir,
            'origin': self.remote_dir,
            'branch': 'master',
        })

    def tearDown(self):
        self.cleanup()

    def test_initialize_repo(self):
        """
        Test that importing from github will create a repo if the repo doesn't already exist
        """
        self.assertEquals(1, len(Repo(self.repo_dir).head.reference.log()))

    def test_import_contents(self):
        """
        Test that the import loads the correct course into the modulestore
        """
        self.assertEquals('Toy Course', self.import_course.metadata['display_name'])
        self.assertIn(
            Location('i4x://edx/local_repo/chapter/Overview'),
            [child.location for child in self.import_course.get_children()])
        self.assertEquals(1, len(self.import_course.get_children()))

    @override_settings(MITX_FEATURES={'GITHUB_PUSH': False})
    def test_export_no_pash(self):
        """
        Test that with the GITHUB_PUSH feature disabled, no content is pushed to the remote
        """
        export_to_github(self.import_course, 'Test no-push')
        self.assertEquals(1, Repo(self.remote_dir).head.commit.count())

    @override_settings(MITX_FEATURES={'GITHUB_PUSH': True})
    def test_export_push(self):
        """
        Test that with GITHUB_PUSH enabled, content is pushed to the remote
        """
        self.import_course.metadata['display_name'] = 'Changed display name'
        export_to_github(self.import_course, 'Test push')
        self.assertEquals(2, Repo(self.remote_dir).head.commit.count())

    @override_settings(MITX_FEATURES={'GITHUB_PUSH': True})
    def test_export_conflict(self):
        """
        Test that if there is a conflict when pushing to the remote repo, nothing is pushed and an exception is raised
        """
        self.import_course.metadata['display_name'] = 'Changed display name'

        remote = Repo(self.remote_dir)
        remote.git.commit(allow_empty=True, m="Testing conflict commit")

        self.assertRaises(GithubSyncError, export_to_github, self.import_course, 'Test push')
        self.assertEquals(2, remote.head.reference.commit.count())
        self.assertEquals("Testing conflict commit\n", remote.head.reference.commit.message)
