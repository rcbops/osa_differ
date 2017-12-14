"""Testing osa-differ."""
import argparse
import json
import subprocess


from git import Repo

import httpretty

from osa_differ import osa_differ

from pytest import raises


class TestOSADiffer(object):
    """Testing osa-differ."""

    def test_arguments_not_enough(self, capsys):
        """Verify that we get an error with missing args."""
        with raises(SystemExit):
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
        """Verify that GitHub URLs without ".git" are unaltered."""
        repo_url = "https://github.com/openstack/openstack-ansible"
        result = osa_differ.get_commit_url(repo_url)
        assert result == repo_url

    def test_commit_url_github_ending_with_dotgit(self):
        """Verify that ".git" is stripped from GitHub URLs."""
        repo_url = "https://github.com/openstack/openstack-ansible.git"
        result = osa_differ.get_commit_url(repo_url)
        assert result == repo_url[:-4]

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
            file.write_text(u"Test", encoding='utf-8')
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
            file.write_text(u"Test", encoding='utf-8')
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
            file.write_text(u"Test", encoding='utf-8')
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
        file.write_text(u"""---
tempest_git_repo: https://git.openstack.org/openstack/tempest
tempest_git_install_branch: 1493c7f0ba49bfccb9ff8516b10a65d949d7462e
tempest_git_project_group: utility_all
""", encoding='utf-8')
        file = p / 'test2.yml'
        file.write_text(u"""---
novncproxy_git_repo: https://github.com/kanaka/novnc
novncproxy_git_install_branch: da82b3426c27bf1a79f671c5825d68ab8c0c5d9f
novncproxy_git_project_group: nova_console
""", encoding='utf-8')
        repo.index.add(['test1.yml', 'test2.yml'])
        repo.index.commit("Test")
        projects = osa_differ.get_projects(path,
                                           'HEAD')
        assert isinstance(projects, list)

    def test_get_roles(self, tmpdir):
        """Verify that we can get OSA role information."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'ansible-role-requirements.yml'
        file.write_text(u"""
- name: apt_package_pinning
  scm: git
  src: https://github.com/openstack/openstack-ansible-apt_package_pinning
  version: master
""", encoding='utf-8')
        repo.index.add(['ansible-role-requirements.yml'])
        repo.index.commit("Test")

        roles = osa_differ.get_roles(path,
                                     'HEAD',
                                     'ansible-role-requirements.yml')
        assert isinstance(roles, list)
        assert roles[0][0] == 'apt_package_pinning'

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
        file.write_text(u'Testing', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        result = osa_differ.validate_commits(path, ['HEAD'])
        assert result

    def test_commit_invalid(self, tmpdir):
        """Verify that we can find valid commits."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        with raises(Exception):
            osa_differ.validate_commits(path, ['HEAD~1'])

    def test_commit_range_valid(self, tmpdir):
        """Verify that we can test a commit range for validity."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing1', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 1')
        file.write_text(u'Testing2', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 2')

        result = osa_differ.validate_commit_range(path, 'HEAD~1', 'HEAD')

        assert result

    def test_commit_range_not_valid(self, tmpdir):
        """Verify that we can test a commit range for validity."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing1', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 1')
        file.write_text(u'Testing2', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 2')

        with raises(Exception):
            osa_differ.validate_commit_range(path, 'HEAD~2', 'HEAD')

    def test_commit_range_flipped(self, tmpdir):
        """Verify that we can test a commit range for validity."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing1', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 1')
        file.write_text(u'Testing2', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 2')

        result = osa_differ.validate_commit_range(path, 'HEAD', 'HEAD~1')

        assert result == 'flip'

    def test_make_osa_report(self, tmpdir):
        """Verify that we can make the OSA header report."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing1', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 1')
        file.write_text(u'Testing2', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 2')

        parser = osa_differ.create_parser()
        args = parser.parse_args(['HEAD~1', 'HEAD'])
        report = osa_differ.make_osa_report(path,
                                            'HEAD~1',
                                            "HEAD",
                                            args)
        assert "HEAD~1" in report
        assert "OpenStack-Ansible Diff Generator" in report

    def test_make_report(self, tmpdir):
        """Verify that we can make a report."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing1', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 1')
        file.write_text(u'Testing2', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 2')

        new_pins = [("test", "http://example.com", "HEAD")]
        old_pins = [("test", "http://example.com", "HEAD~1")]

        report = osa_differ.make_report(str(tmpdir), old_pins, new_pins)

        assert "1 commit was found in `test <http://example.com>`" in report
        assert "Testing 2" in report

    def test_make_report_old_pin_missing(self, tmpdir):
        """Verify that we can make a report when the old pin is missing."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing1', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 1')
        file.write_text(u'Testing2', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing 2')

        new_pins = [("test", "http://example.com", "HEAD")]
        old_pins = []

        report = osa_differ.make_report(str(tmpdir), old_pins, new_pins)

        assert report == ''

    def test_publish_report(self):
        """Verify that we can publish a report to stdout."""
        report = "Sample report"

        parser = osa_differ.create_parser()
        args = parser.parse_args(['HEAD~1', 'HEAD'])

        result = osa_differ.publish_report(report, args, 'HEAD~1', 'HEAD')

        assert result == 'Sample report'

    def test_publish_report_quiet(self):
        """Verify that we can skip publishing to stdout."""
        report = "Sample report"

        parser = osa_differ.create_parser()
        args = parser.parse_args(['HEAD~1', 'HEAD', '--quiet'])

        result = osa_differ.publish_report(report, args, 'HEAD~1', 'HEAD')

        assert result == ''

    def test_publish_report_to_file(self, tmpdir):
        """Verify that we can write a report to a file."""
        report = "Sample report"

        p = tmpdir.mkdir('test')

        parser = osa_differ.create_parser()
        filearg = "{0}/test.rst".format(str(p))
        args = parser.parse_args(['HEAD~1', 'HEAD', '--file', filearg])

        result = osa_differ.publish_report(report, args, 'HEAD~1', 'HEAD')

        assert 'Report written to file' in result
        assert 'test.rst' in result

    @httpretty.activate
    def test_publish_report_to_gist(self):
        """Verify that we can post the report to a gist."""
        json_body = {
            'html_url': 'https://example.com/'
        }
        httpretty.register_uri(httpretty.POST,
                               "https://api.github.com/gists",
                               body=json.dumps(json_body))

        report = "Sample report"

        parser = osa_differ.create_parser()
        args = parser.parse_args(['HEAD~1', 'HEAD', '--gist'])

        result = osa_differ.publish_report(report, args, 'HEAD~1', 'HEAD')

        assert 'Report posted to GitHub Gist' in result

    def test_prepare_storage_directory_exists(self, tmpdir):
        """Verify that we can create a storage directory."""
        p = tmpdir.mkdir("test")
        storagedir = osa_differ.prepare_storage_dir(str(p))
        assert storagedir == p

    def test_prepare_storage_directory_create(self, tmpdir):
        """Verify that we can create a storage directory."""
        p = tmpdir.mkdir("test")
        newdir = "{0}/subdir".format(str(p))
        storagedir = osa_differ.prepare_storage_dir(newdir)
        assert storagedir == newdir

    def test_prepare_storage_directory_exception(self, tmpdir):
        """Verify that we can create a storage directory."""
        p = tmpdir.mkdir("test")
        newdir = "{0}/subdir/subdir/subdir".format(str(p))

        with raises(OSError):
            osa_differ.prepare_storage_dir(newdir)

    def test_render_template(self, tmpdir):
        """Verify that we can render a jinja template."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        for x in range(0, 10):
            file = p / "test{0}.txt".format(x)
            file.write_text(u"Test", encoding='utf-8')
            repo.index.add(['test{0}.txt'.format(x)])
            repo.index.commit("Commit #{0}".format(x))

        commits = osa_differ.get_commits(path, 'HEAD~2', 'HEAD')

        template_vars = {
            'repo': 'openstack-ansible',
            'commits': commits,
            'commit_base_url': 'http://example.com',
            'old_sha': 'HEAD~10',
            'new_sha': 'HEAD~1'
        }
        template_filename = "offline-repo-changes.j2"
        rst = osa_differ.render_template(template_filename,
                                         template_vars)
        assert "openstack-ansible" in rst
        assert "2 commits were found" in rst
        assert "http://example.com" in rst
        assert "HEAD~10" in rst
        assert "HEAD~1" in rst

    def test_repo_clone(self, tmpdir, monkeypatch):
        """Verify that we can clone a repo."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing', encoding='utf-8')
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
        file.write_text(u'Testing', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')

        p = tmpdir.mkdir("test2")
        path_clonefrom = "{0}/testrepodoesntexist".format(str(p))
        result = osa_differ.update_repo(path_clonefrom, path)

        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_repo_update_update(self, tmpdir):
        """Verify that update_repo tries to update the repo."""
        p = tmpdir.mkdir('test')
        path = str(p)
        repo = Repo.init(path)
        file = p / 'test.txt'
        file.write_text(u'Testing', encoding='utf-8')
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
        file.write_text(u'Testing', encoding='utf-8')
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
        file.write_text(u'Testing', encoding='utf-8')
        repo.index.add(['test.txt'])
        repo.index.commit('Testing')
        repo.create_remote('origin', url='http://example.com')

        monkeypatch.setattr(
            "git.cmd.Git._call_process", lambda *args, **kwargs: True)
        result = osa_differ.repo_pull(path,
                                      "http://example.com",
                                      fetch=True)
        monkeypatch.undo()
        assert result.active_branch.name == 'master'
        assert not result.is_dirty()

    def test_get_release_notes(self, tmpdir):
        """Ensure getting release notes works."""
        p = tmpdir.mkdir('releasenotes')
        tmpdir.mkdir('releasenotes/notes')
        path = str(p)
        repo = Repo.init(path)
        repo.git.config("user.name", "Chuck Norris")
        repo.git.config("user.email", "chuck.norris@example.com")
        file1 = p / 'almost_there.txt'
        file1.write_text(u'almost there', encoding='utf-8')
        reno_add1_command = ["reno", "new", "test-note1"]
        reno_add1_p = subprocess.Popen(reno_add1_command,
                                       stdout=subprocess.PIPE,
                                       cwd=path)
        reno_new_output1 = reno_add1_p.communicate()[0].decode('UTF-8')
        release_file_path = reno_new_output1.split(" ")[-1].rstrip()
        content41 = (u'---\n'
                     u'features:\n'
                     u'  - Autonomous behavior is now default in the\n'
                     u'    Transportation class\n'
                     u'  - The Person worker class now uses a new algorithm\n'
                     u'    to generate the value attribute. Value is now\n'
                     u'    given a default of 100 for all Person threads\n'
                     u'fixes:\n'
                     u'  - Fixed a race condition where Person.hope was\n'
                     u'    sometimes set to 0\n'
                     u'deprecations:\n'
                     u'  - The road_rage function in the Transportation\n'
                     u'    class is now deprecated')
        with open('{}/{}'.format(path, release_file_path), "w") as f:
            f.write(content41)

        repo.index.add(['almost_there.txt'])
        repo.index.add(['{}'.format(release_file_path)])
        ref = repo.index.commit('Fixed issue1')
        repo.create_tag("41.0.0",
                        ref=ref,
                        message="Almost there, but not quite.",
                        force=True)
        file2 = p / 'there.txt'
        file2.write_text(u'almost there', encoding='utf-8')
        reno_add2_command = ["reno", "new", "test-note2"]
        reno_add2_p = subprocess.Popen(reno_add2_command,
                                       stdout=subprocess.PIPE,
                                       cwd=path)
        reno_new_output2 = reno_add2_p.communicate()[0].decode('UTF-8')
        release_file_path = reno_new_output2.split(" ")[-1].rstrip()
        content42 = (u'---\n'
                     u'features:\n'
                     u'  - World peace has been added in version 42.0.0.\n'
                     u'    This is enabled by default\n'
                     u'  - The Greed class has been completely suppressed.\n'
                     u'    Any attributes generated by the Greed class are\n'
                     u'    now automatically garbage collected.\n'
                     u'  - The FoodGenerator class now has been optimized to\n'
                     u'    run at peak performance.\n'
                     u'fixes:\n'
                     u'  - Fixed issue in Ozone class related to pollution\n'
                     u'  - Fixed common issue in Politicians class where\n'
                     u'    Person.iq was sometimes set to 20')
        with open('{}/{}'.format(path, release_file_path), "w") as f:
            f.write(content42)
        repo.index.add(['there.txt', release_file_path])
        repo.index.commit('Fixed issue2')
        repo.create_tag("42.0.0", message="Perfect.", force=True)
        reno_output = osa_differ.get_release_notes(path, '41.0.0', '42.0.0')
        assert "41.0.0" in reno_output
        assert "42.0.0" in reno_output
