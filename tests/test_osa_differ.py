"""Testing osa-differ."""
import argparse
from git import Repo
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
        assert "usage" in err

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

    def test_get_commits(self, tmpdir):
        """Verify that we can get commits for a repo."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        for x in range(0, 10):
            file = p / "test{0}.txt".format(x)
            file.write_text("Test", encoding='ascii')
            repo.index.add(['test{0}.txt'.format(x)])
            repo.index.commit("Commit #{0}".format(x))

        commits = osa_differ.get_commits(path, 'HEAD~2', 'HEAD')
        assert len(list(commits)) == 2

    def test_get_commits_hide_merges(self, tmpdir):
        """Verify that we can get commits for a repo."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        for x in range(0, 10):
            file = p / "test{0}.txt".format(x)
            file.write_text("Test", encoding='ascii')
            repo.index.add(['test{0}.txt'.format(x)])
            repo.index.commit("Merge #{0}".format(x))

        commits = osa_differ.get_commits(path, 'HEAD~2', 'HEAD',
                                         hide_merges=True)
        assert len(list(commits)) == 0

    def test_get_commits_include_merges(self, tmpdir):
        """Verify that we can get commits for a repo."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        for x in range(0, 10):
            file = p / "test{0}.txt".format(x)
            file.write_text("Test", encoding='ascii')
            repo.index.add(['test{0}.txt'.format(x)])
            repo.index.commit("Merge #{0}".format(x))

        commits = osa_differ.get_commits(path, 'HEAD~2', 'HEAD',
                                         hide_merges=False)
        assert len(list(commits)) == 2

    def test_get_projects(self, tmpdir):
        """Verify that we can retrieve projects."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test1.yml'
        file.write_text("""---
tempest_git_repo: https://git.openstack.org/openstack/tempest
tempest_git_install_branch: 1493c7f0ba49bfccb9ff8516b10a65d949d7462e
tempest_git_project_group: utility_all
""", encoding='ascii')
        file = p / 'test2.yml'
        file.write_text("""---
novncproxy_git_repo: https://github.com/kanaka/novnc
novncproxy_git_install_branch: da82b3426c27bf1a79f671c5825d68ab8c0c5d9f
novncproxy_git_project_group: nova_console
""", encoding='ascii')
        repo.index.add(['test1.yml', 'test2.yml'])
        repo.index.commit("Test")
        projects = osa_differ.get_projects(path,
                                           ['test1.yml', 'test2.yml'],
                                           'HEAD')
        assert isinstance(projects, dict)

    def test_get_roles(self, tmpdir):
        """Verify that we can get OSA role information."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'ansible-role-requirements.yml'
        file.write_text("""
- name: apt_package_pinning
  scm: git
  version: master
""", encoding='ascii')
        repo.index.add(['ansible-role-requirements.yml'])
        repo.index.commit("Test")

        roles = osa_differ.get_roles(path, 'HEAD')
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

    def test_commit_valid(self, tmpdir):
        """Verify that we can find valid commits."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text('Testing', encoding='ascii')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        result = osa_differ.valid_commit(path, 'HEAD')
        assert result

    def test_commit_invalid(self, tmpdir):
        """Verify that we can find valid commits."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text('Testing', encoding='ascii')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        result = osa_differ.valid_commit(path, 'HEAD~1')
        assert not result

    def test_repo_clone(self, tmpdir, monkeypatch):
        """Verify that we can clone a repo."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text('Testing', encoding='ascii')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        def mockclone(x, y):
            return path

        def mockwait(*args, **kwargs):
            return True

        monkeypatch.setattr("git.repo.base.Repo.clone", mockclone)
        monkeypatch.setattr("git.cmd.Git.AutoInterrupt.wait", mockwait)
        result = osa_differ.repo_clone(path,
                                       "http://example.com")

        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_clone_update(self, tmpdir):
        """Verify that we can clone a repo."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text('Testing', encoding='ascii')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        p = tmpdir.mkdir("test2")
        repo_path = p / "test"
        path_clonefrom = str(repo_path)
        result = osa_differ.update_repo(path, path_clonefrom)

        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_update_update(self, tmpdir):
        """Verify that update_repo tries to update the repo."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text('Testing', encoding='ascii')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        result = osa_differ.update_repo(path, path)

        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_update_without_fetch(self, tmpdir):
        """Verify that we can get a repo ready without fetching it."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text('Testing', encoding='ascii')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        result = osa_differ.repo_pull(path,
                                      "http://example.com",
                                      fetch=False)
        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_update_with_fetch(self, tmpdir, monkeypatch):
        """Verify that we can get a repo ready and update it."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text('Testing', encoding='ascii')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')
        repo.create_remote('origin', url='http://example.com')

        monkeypatch.setattr("git.remote.Remote.pull", lambda x: True)
        result = osa_differ.repo_pull(path,
                                      "http://example.com",
                                      fetch=True)
        assert result.active_branch.name == 'master'
        assert not result.is_dirty()
