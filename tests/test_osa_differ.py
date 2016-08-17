"""Testing osa-differ."""
import argparse
import httpretty
import json
from osa_differ import osa_differ
import pytest


class TestOSADiffer(object):
    """Testing osa-differ."""

    def test_arguments_not_enough(self, capsys):
        """Verify that we get an error with missing args."""
        with pytest.raises(SystemExit):
            parser = osa_differ.create_parser()
            parser.parse_args([])
        out, err = capsys.readouterr()
        assert "too few arguments" in err

    def test_arguments_sufficient(self):
        """Verify that we get args properly with right args passed."""
        parser = osa_differ.create_parser()
        args = vars(parser.parse_args(['13.3.0', '13.3.1']))
        assert args['old_commit'][0] == '13.3.0'
        assert args['new_commit'][0] == '13.3.1'

    def test_arguments_parse(self, monkeypatch):
        """Test if we can parse arguments."""
        def mockreturn(test):
            return {'test': 'test'}
        monkeypatch.setattr('argparse.ArgumentParser.parse_args', mockreturn)
        result = osa_differ.parse_arguments()
        assert result['test'] == 'test'

    def test_create_parser(self):
        """Verify that we can create an argument parser."""
        parser = osa_differ.create_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_commit_url_github(self):
        """Verify that GitHub URLs are unaltered."""
        repo_url = "https://github.com/openstack/openstack-ansible"
        result = osa_differ.get_commit_url(repo_url)
        assert result == repo_url

    def test_commit_url_openstack(self):
        """Verify that OpenStack URLs are fixed."""
        repo_url = "https://git.openstack.org/cgit/openstack/openstack-ansible"
        result = osa_differ.get_commit_url(repo_url)
        assert result == "https://github.com/openstack/openstack-ansible"

    def test_commit_url_unknown(self):
        """Verify that unknown URLs are unaltered."""
        repo_url = "https://reddit.com"
        result = osa_differ.get_commit_url(repo_url)
        assert result == repo_url

    def test_get_commits(self, git_repo):
        """Verify that we can get commits for a repo."""
        path = git_repo.workspace
        for x in range(0, 10):
            file = path / "test{1}.txt".format(path, x)
            file.write_text("Test")
            git_repo.run('git add test{0}.txt'.format(x))
            git_repo.api.index.commit("Commit #{0}".format(x))

        commits = osa_differ.get_commits(git_repo.workspace, 'HEAD~2', 'HEAD')
        assert len(list(commits)) == 2

    def test_get_commits_hide_merges(self, git_repo):
        """Verify that we can get commits for a repo."""
        path = git_repo.workspace
        for x in range(0, 10):
            file = path / "test{1}.txt".format(path, x)
            file.write_text("Test")
            git_repo.run('git add test{0}.txt'.format(x))
            git_repo.api.index.commit("Merge #{0}".format(x))

        commits = osa_differ.get_commits(git_repo.workspace, 'HEAD~2', 'HEAD',
                                         hide_merges=True)
        assert len(list(commits)) == 0

    def test_get_commits_include_merges(self, git_repo):
        """Verify that we can get commits for a repo."""
        path = git_repo.workspace
        for x in range(0, 10):
            file = path / "test{1}.txt".format(path, x)
            file.write_text("Test")
            git_repo.run('git add test{0}.txt'.format(x))
            git_repo.api.index.commit("Merge #{0}".format(x))

        commits = osa_differ.get_commits(git_repo.workspace, 'HEAD~2', 'HEAD',
                                         hide_merges=False)
        assert len(list(commits)) == 2

    def test_get_projects(self, git_repo):
        """Verify that we can retrieve projects."""
        path = git_repo.workspace
        file = path / 'test1.yml'
        file.write_text("""---
tempest_git_repo: https://git.openstack.org/openstack/tempest
tempest_git_install_branch: 1493c7f0ba49bfccb9ff8516b10a65d949d7462e
tempest_git_project_group: utility_all
""")
        file = path / 'test2.yml'
        file.write_text("""---
novncproxy_git_repo: https://github.com/kanaka/novnc
novncproxy_git_install_branch: da82b3426c27bf1a79f671c5825d68ab8c0c5d9f
novncproxy_git_project_group: nova_console
""")
        git_repo.run('git add test1.yml')
        git_repo.api.index.commit("Test")
        projects = osa_differ.get_projects(git_repo.workspace,
                                           ['test1.yml', 'test2.yml'],
                                           'HEAD')
        assert isinstance(projects, dict)

    def test_get_roles(self, git_repo):
        """Verify that we can get OSA role information."""
        path = git_repo.workspace
        file = path / 'ansible-role-requirements.yml'
        file.write_text("""
- name: apt_package_pinning
  scm: git
  version: master
""")
        git_repo.run('git add ansible-role-requirements.yml')
        git_repo.api.index.commit("Test")

        roles = osa_differ.get_roles(git_repo.workspace, 'HEAD')
        assert isinstance(roles, list)
        assert roles[0]['name'] == 'apt_package_pinning'

    def test_logger_setup(self):
        """Verify that we can create a logger."""
        logger = osa_differ.get_logger()
        assert logger.level == 0

    def test_logger_setup_debug(self):
        """Verify that we can create a debug logger."""
        logger = osa_differ.get_logger(debug=True)
        assert logger.level == 10

    @httpretty.activate
    def test_post_gist(self):
        """Verify that posting gists works."""
        json_body = {
            'html_url': 'https://example.com/'
        }
        httpretty.register_uri(httpretty.POST,
                               "https://api.github.com/gists",
                               body=json.dumps(json_body))
        result = osa_differ.post_gist("report text", 'HEAD~1', 'HEAD')
        assert result == 'https://example.com/'

    def test_commit_valid(self, git_repo):
        """Verify that we can find valid commits."""
        path = git_repo.workspace
        file = path / 'test.txt'
        file.write_text('Testing')
        git_repo.run('git add test.txt')
        git_repo.api.index.commit("Testing")

        result = osa_differ.valid_commit(git_repo.workspace, 'HEAD')
        assert result

    def test_commit_invalid(self, git_repo):
        """Verify that we can find valid commits."""
        path = git_repo.workspace
        file = path / 'test.txt'
        file.write_text('Testing')
        git_repo.run('git add test.txt')
        git_repo.api.index.commit("Testing")

        result = osa_differ.valid_commit(git_repo.workspace, 'HEAD~1')
        assert not result

    def test_repo_clone(self, git_repo, monkeypatch):
        """Verify that we can clone a repo."""
        path = git_repo.workspace
        file = path / 'test.txt'
        file.write_text('Testing')
        git_repo.run('git add test.txt')
        git_repo.api.index.commit("Testing")

        def mockclone(x, y):
            return git_repo

        def mockwait(*args, **kwargs):
            return True

        monkeypatch.setattr("git.repo.base.Repo.clone", mockclone)
        monkeypatch.setattr("git.cmd.Git.AutoInterrupt.wait", mockwait)
        result = osa_differ.repo_clone(git_repo.workspace,
                                       "http://example.com")

        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_clone_update(self, git_repo, tmpdir):
        """Verify that we can clone a repo."""
        path = git_repo.workspace
        file = path / 'test.txt'
        file.write_text('Testing')
        git_repo.run('git add test.txt')
        git_repo.api.index.commit("Testing")

        p = tmpdir.mkdir("test")
        repo_path = p / "test"
        result = osa_differ.update_repo(str(repo_path), git_repo.workspace)

        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_update_update(self, git_repo, tmpdir):
        """Verify that update_repo tries to update the repo."""
        path = git_repo.workspace
        file = path / 'test.txt'
        file.write_text('Testing')
        git_repo.run('git add test.txt')
        git_repo.api.index.commit("Testing")

        result = osa_differ.update_repo(git_repo.workspace, git_repo.workspace)

        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_update_without_fetch(self, git_repo):
        """Verify that we can get a repo ready without fetching it."""
        path = git_repo.workspace
        file = path / 'test.txt'
        file.write_text('Testing')
        git_repo.run('git add test.txt')
        git_repo.api.index.commit("Testing")

        result = osa_differ.repo_pull(git_repo.workspace,
                                      "http://example.com",
                                      fetch=False)
        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_update_with_fetch(self, git_repo, monkeypatch):
        """Verify that we can get a repo ready and update it."""
        path = git_repo.workspace
        file = path / 'test.txt'
        file.write_text('Testing')
        git_repo.run('git add test.txt')
        git_repo.api.index.commit("Testing")
        git_repo.api.create_remote('origin', git_repo.workspace)

        monkeypatch.setattr("git.remote.Remote.pull", lambda x: True)
        result = osa_differ.repo_pull(git_repo.workspace,
                                      "http://example.com",
                                      fetch=True)
        assert result.active_branch.name == 'master'
        assert not result.is_dirty()
