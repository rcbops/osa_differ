#!/usr/bin/env python
# Copyright 2016, Major Hayden
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Analyzes the differences between two OpenStack-Ansible commits."""
import argparse
import glob
import json
import logging
import os
import re
import subprocess
import sys
from distutils.version import LooseVersion

from git import Repo

import jinja2

import requests

import yaml

from . import exceptions


# Configure logging
log = logging.getLogger()
log.setLevel(logging.ERROR)


def create_parser():
    """Create argument parser."""
    description = """Generate OpenStack-Ansible Diff
----------------------------------------

Finds changes in OpenStack projects and OpenStack-Ansible roles between two
commits in OpenStack-Ansible.

"""

    parser = argparse.ArgumentParser(
        usage='%(prog)s',
        description=description,
        epilog='Licensed "Apache 2.0"',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'old_commit',
        action='store',
        nargs=1,
        help="Git SHA of the older commit",
    )
    parser.add_argument(
        'new_commit',
        action='store',
        nargs=1,
        help="Git SHA of the newer commit",
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        default=False,
        help="Enable info output",
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=False,
        help="Enable debug output",
    )
    parser.add_argument(
        '-d', '--directory',
        action='store',
        default="~/.osa-differ",
        help="Git repo storage directory (default: ~/.osa-differ)",
    )
    parser.add_argument(
        '-rr', '--role-requirements',
        action='store',
        default='ansible-role-requirements.yml',
        help="Name of the ansible role requirements file to read",
    )
    parser.add_argument(
        '-u', '--update',
        action='store_true',
        default=False,
        help="Fetch latest changes to repo",
    )
    parser.add_argument(
        '--osa-repo-url',
        action='store',
        default='https://git.openstack.org/openstack/openstack-ansible',
        help="URL of the openstack-ansible git repo",
    )
    display_opts = parser.add_argument_group("Limit scope")
    display_opts.add_argument(
        "--skip-projects",
        action="store_true",
        help="Skip checking for changes in OpenStack projects"
    )
    display_opts.add_argument(
        "--skip-roles",
        action="store_true",
        help="Skip checking for changes in OpenStack-Ansible roles"
    )
    release_note_opts = parser.add_argument_group("Release notes")
    release_note_opts.add_argument(
        "--release-notes",
        action="store_true",
        help=("Print reno release notes for OpenStack-Ansible "
              "between the two commits")
    )
    output_desc = ("Output is printed to stdout by default.")
    output_opts = parser.add_argument_group('Output options', output_desc)
    output_opts.add_argument(
        '--quiet',
        action='store_true',
        default=False,
        help="Do not output to stdout",
    )
    output_opts.add_argument(
        '--gist',
        action='store_true',
        default=False,
        help="Output into a GitHub Gist",
    )
    output_opts.add_argument(
        '--file',
        metavar="FILENAME",
        action='store',
        help="Output to a file",
    )
    return parser


def get_commits(repo_dir, old_commit, new_commit, hide_merges=True):
    """Find all commits between two commit SHAs."""
    repo = Repo(repo_dir)
    commits = repo.iter_commits(rev="{0}..{1}".format(old_commit, new_commit))
    if hide_merges:
        return [x for x in commits if not x.summary.startswith("Merge ")]
    else:
        return list(commits)


def get_commit_url(repo_url):
    """Determine URL to view commits for repo."""
    if "github.com" in repo_url:
        return repo_url[:-4] if repo_url.endswith(".git") else repo_url
    if "git.openstack.org" in repo_url:
        uri = '/'.join(repo_url.split('/')[-2:])
        return "https://github.com/{0}".format(uri)

    # If it didn't match these conditions, just return it.
    return repo_url


def get_projects(osa_repo_dir, commit):
    """Get all projects from multiple YAML files."""
    # Check out the correct commit SHA from the repository
    repo = Repo(osa_repo_dir)
    checkout(repo, commit)

    yaml_files = glob.glob(
        '{0}/playbooks/defaults/repo_packages/*.yml'.format(osa_repo_dir)
    )
    yaml_parsed = []
    for yaml_file in yaml_files:
        with open(yaml_file, 'r') as f:
            yaml_parsed.append(yaml.load(f))

    merged_dicts = {k: v for d in yaml_parsed for k, v in d.items()}

    return normalize_yaml(merged_dicts)


def checkout(repo, ref):
    """Checkout a repoself."""
    # Delete local branch if it exists, remote branch will be tracked
    # automatically. This prevents stale local branches from causing problems.
    # It also avoids problems with appending origin/ to refs as that doesn't
    # work with tags, SHAs, and upstreams not called origin.
    if ref in repo.branches:
        # eg delete master but leave origin/master
        log.warn("Removing local branch {b} for repo {r}".format(b=ref,
                                                                 r=repo))
        # Can't delete currently checked out branch, so make sure head is
        # detached before deleting.

        repo.head.reset(index=True, working_tree=True)
        repo.git.checkout(repo.head.commit.hexsha)
        repo.delete_head(ref, '--force')

    log.info("Checkout out repo {repo} to ref {ref}".format(repo=repo,
                                                            ref=ref))
    repo.head.reset(index=True, working_tree=True)
    repo.git.checkout(ref)
    repo.head.reset(index=True, working_tree=True)
    sha = repo.head.commit.hexsha
    log.info("Current SHA for repo {repo} is {sha}".format(repo=repo, sha=sha))


def get_roles(osa_repo_dir, commit, role_requirements):
    """Read OSA role information at a particular commit."""
    repo = Repo(osa_repo_dir)

    checkout(repo, commit)

    log.info("Looking for file {f} in repo {r}".format(r=osa_repo_dir,
                                                       f=role_requirements))
    filename = "{0}/{1}".format(osa_repo_dir, role_requirements)
    with open(filename, 'r') as f:
        roles_yaml = yaml.load(f)

    return normalize_yaml(roles_yaml)


def make_osa_report(repo_dir, old_commit, new_commit,
                    args):
    """Create initial RST report header for OpenStack-Ansible."""
    update_repo(repo_dir, args.osa_repo_url, args.update)

    # Are these commits valid?
    validate_commits(repo_dir, [old_commit, new_commit])

    # Do we have a valid commit range?
    validate_commit_range(repo_dir, old_commit, new_commit)

    # Get the commits in the range
    commits = get_commits(repo_dir, old_commit, new_commit)

    # Start off our report with a header and our OpenStack-Ansible commits.
    template_vars = {
        'args': args,
        'repo': 'openstack-ansible',
        'commits': commits,
        'commit_base_url': get_commit_url(args.osa_repo_url),
        'old_sha': old_commit,
        'new_sha': new_commit
    }
    return render_template('offline-header.j2', template_vars)


def make_report(storage_directory, old_pins, new_pins, do_update=False):
    """Create RST report from a list of projects/roles."""
    report = ""
    for new_pin in new_pins:
        repo_name, repo_url, commit_sha = new_pin

        # Prepare our repo directory and clone the repo if needed. Only pull
        # if the user requests it.
        repo_dir = "{0}/{1}".format(storage_directory, repo_name)
        update_repo(repo_dir, repo_url, do_update)

        # Get the old SHA from the previous pins. If this pin didn't exist
        # in the previous OSA revision, skip it. This could happen with newly-
        # added projects and roles.
        try:
            commit_sha_old = next(x[2] for x in old_pins if x[0] == repo_name)
        except Exception:
            continue

        # Loop through the commits and render our template.
        validate_commits(repo_dir, [commit_sha_old, commit_sha])
        commits = get_commits(repo_dir, commit_sha_old, commit_sha)
        template_vars = {
            'repo': repo_name,
            'commits': commits,
            'commit_base_url': get_commit_url(repo_url),
            'old_sha': commit_sha_old,
            'new_sha': commit_sha
        }
        rst = render_template('offline-repo-changes.j2', template_vars)
        report += rst

    return report


def normalize_yaml(yaml):
    """Normalize the YAML from project and role lookups.

    These are returned as a list of tuples.
    """
    if isinstance(yaml, list):
        # Normalize the roles YAML data
        normalized_yaml = [(x['name'], x['src'], x.get('version', 'HEAD'))
                           for x in yaml]
    else:
        # Extract the project names from the roles YAML and create a list of
        # tuples.
        projects = [x[:-9] for x in yaml.keys() if x.endswith('git_repo')]
        normalized_yaml = []
        for project in projects:
            repo_url = yaml['{0}_git_repo'.format(project)]
            commit_sha = yaml['{0}_git_install_branch'.format(project)]
            normalized_yaml.append((project, repo_url, commit_sha))

    return normalized_yaml


def parse_arguments():
    """Parse arguments."""
    parser = create_parser()
    args = parser.parse_args()
    return args


def post_gist(report_data, old_sha, new_sha):
    """Post the report to a GitHub Gist and return the URL of the gist."""
    payload = {
        "description": ("Changes in OpenStack-Ansible between "
                        "{0} and {1}".format(old_sha, new_sha)),
        "public": True,
        "files": {
            "osa-diff-{0}-{1}.rst".format(old_sha, new_sha): {
                "content": report_data
            }
        }
    }
    url = "https://api.github.com/gists"
    r = requests.post(url, data=json.dumps(payload))
    response = r.json()
    return response['html_url']


def publish_report(report, args, old_commit, new_commit):
    """Publish the RST report based on the user request."""
    # Print the report to stdout unless the user specified --quiet.
    output = ""

    if not args.quiet and not args.gist and not args.file:
        return report

    if args.gist:
        gist_url = post_gist(report, old_commit, new_commit)
        output += "\nReport posted to GitHub Gist: {0}".format(gist_url)

    if args.file is not None:
        with open(args.file, 'w') as f:
            f.write(report)
        output += "\nReport written to file: {0}".format(args.file)

    return output


def prepare_storage_dir(storage_directory):
    """Prepare the storage directory."""
    storage_directory = os.path.expanduser(storage_directory)
    if not os.path.exists(storage_directory):
        os.mkdir(storage_directory)

    return storage_directory


def render_template(template_file, template_vars):
    """Render a jinja template."""
    # Load our Jinja templates
    template_dir = "{0}/templates".format(
        os.path.dirname(os.path.abspath(__file__))
    )
    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        trim_blocks=True
    )
    rendered = jinja_env.get_template(template_file).render(template_vars)

    return rendered


def repo_clone(repo_dir, repo_url):
    """Clone repository to this host."""
    repo = Repo.clone_from(repo_url, repo_dir)
    return repo


def repo_pull(repo_dir, repo_url, fetch=False):
    """Reset repository and optionally update it."""
    # Make sure the repository is reset to the master branch.
    repo = Repo(repo_dir)
    repo.git.clean("-df")
    repo.git.reset("--hard")
    repo.git.checkout("master")
    repo.head.reset(index=True, working_tree=True)

    # Compile the refspec appropriately to ensure
    # that if the repo is from github it includes
    # all the refs needed, including PR's.
    refspec_list = [
        "+refs/heads/*:refs/remotes/origin/*",
        "+refs/heads/*:refs/heads/*",
        "+refs/tags/*:refs/tags/*"
    ]
    if "github.com" in repo_url:
        refspec_list.extend([
            "+refs/pull/*:refs/remotes/origin/pr/*",
            "+refs/heads/*:refs/remotes/origin/*"])

    # Only get the latest updates if requested.
    if fetch:
        repo.git.fetch(["-u", "-v", "-f",
                        repo_url,
                        refspec_list])
    return repo


def update_repo(repo_dir, repo_url, fetch=False):
    """Clone the repo if it doesn't exist already, otherwise update it."""
    repo_exists = os.path.exists(repo_dir)
    if not repo_exists:
        log.info("Cloning repo {}".format(repo_url))
        repo = repo_clone(repo_dir, repo_url)

    # Make sure the repo is properly prepared
    # and has all the refs required
    log.info("Fetching repo {} (fetch: {})".format(repo_url, fetch))
    repo = repo_pull(repo_dir, repo_url, fetch)

    return repo


def validate_commits(repo_dir, commits):
    """Test if a commit is valid for the repository."""
    log.debug("Validating {c} exist in {r}".format(c=commits, r=repo_dir))
    repo = Repo(repo_dir)
    for commit in commits:
        try:
            commit = repo.commit(commit)
        except Exception:
            msg = ("Commit {commit} could not be found in repo {repo}. "
                   "You may need to pass --update to fetch the latest "
                   "updates to the git repositories stored on "
                   "your local computer.".format(repo=repo_dir, commit=commit))
            raise exceptions.InvalidCommitException(msg)

    return True


def validate_commit_range(repo_dir, old_commit, new_commit):
    """Check if commit range is valid. Flip it if needed."""
    # Are there any commits between the two commits that were provided?
    try:
        commits = get_commits(repo_dir, old_commit, new_commit)
    except Exception:
        commits = []
    if len(commits) == 0:
        # The user might have gotten their commits out of order. Let's flip
        # the order of the commits and try again.
        try:
            commits = get_commits(repo_dir, new_commit, old_commit)
        except Exception:
            commits = []
        if len(commits) == 0:
            # Okay, so there really are no commits between the two commits
            # provided by the user. :)
            msg = ("The commit range {0}..{1} is invalid for {2}."
                   "You may need to use the --update option to fetch the "
                   "latest updates to the git repositories stored on your "
                   "local computer.".format(old_commit, new_commit, repo_dir))
            raise exceptions.InvalidCommitRangeException(msg)
        else:
            return 'flip'

    return True


def get_release_notes(osa_repo_dir, osa_old_commit, osa_new_commit):
    """Get release notes between the two revisions."""
    repo = Repo(osa_repo_dir)

    # Get a list of tags, sorted
    tags = repo.git.tag().split('\n')
    tags = sorted(tags, key=LooseVersion)
    # Currently major tags are being printed after rc and
    # b tags. We need to fix the list so that major
    # tags are printed before rc and b releases
    tags = _fix_tags_list(tags)

    # Find the closest tag from a given SHA
    # The tag found here is the tag that was cut
    # either on or before the given SHA
    checkout(repo, osa_old_commit)
    old_tag = repo.git.describe()

    # If the SHA given is between two release tags, then
    # 'git describe' will return a tag in form of
    # <tag>-<commitNum>-<sha>. For example:
    # 14.0.2-3-g6931e26
    # Since reno does not support this format, we need to
    # strip away the commit number and sha bits.
    if '-' in old_tag:
        old_tag = old_tag[0:old_tag.index('-')]

    # Get the nearest tag associated with the new commit
    checkout(repo, osa_new_commit)
    new_tag = repo.git.describe()
    if '-' in new_tag:
        nearest_new_tag = new_tag[0:new_tag.index('-')]
    else:
        nearest_new_tag = new_tag

    # Truncate the tags list to only include versions
    # between old_sha and new_sha. The latest release
    # is not included in this list. That version will be
    # printed separately in the following step.
    tags = tags[tags.index(old_tag):tags.index(nearest_new_tag)]

    release_notes = ""
    # Checkout the new commit, then run reno to get the latest
    # releasenotes that have been created or updated between
    # the latest release and this new commit.
    repo.git.checkout(osa_new_commit, '-f')
    reno_report_command = ['reno',
                           'report',
                           '--earliest-version',
                           nearest_new_tag]
    reno_report_p = subprocess.Popen(reno_report_command,
                                     cwd=osa_repo_dir,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
    reno_output = reno_report_p.communicate()[0].decode('UTF-8')
    release_notes += reno_output

    # We want to start with the latest packaged release first, so
    # the tags list is reversed
    for version in reversed(tags):
        # If version is an rc or b tag, and it has a major
        # release tag, then skip it. There is no need to print
        # release notes for an rc or b release unless we are
        # comparing shas between two rc or b releases.
        repo.git.checkout(version, '-f')
        # We are outputing one version at a time here
        reno_report_command = ['reno',
                               'report',
                               '--branch',
                               version,
                               '--earliest-version',
                               version]
        reno_report_p = subprocess.Popen(reno_report_command,
                                         cwd=osa_repo_dir,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
        reno_output = reno_report_p.communicate()[0].decode('UTF-8')
        # We need to ensure the output includes the version we are concerned
        # about.
        # This is due to https://bugs.launchpad.net/reno/+bug/1670173
        if version in reno_output:
            release_notes += reno_output

    # Clean up "Release Notes" title. We don't need this title for
    # each tagged release.
    release_notes = release_notes.replace(
        "=============\nRelease Notes\n=============",
        ""
    )
    # Replace headers that contain '=' with '~' to comply with osa-differ's
    # formatting
    release_notes = re.sub('===+', _equal_to_tilde, release_notes)
    # Replace headers that contain '-' with '#' to comply with osa-differ's
    # formatting
    release_notes = re.sub('\---+', _dash_to_num, release_notes)
    return release_notes


def _equal_to_tilde(matchobj):
    num_of_equal = len(matchobj.group(0))
    return '~' * num_of_equal


def _dash_to_num(matchobj):
    num_of_dashes = len(matchobj.group(0))
    return '#' * num_of_dashes


def _fix_tags_list(tags):
    new_list = []
    for tag in tags:
        rc_releases = []
        # Ignore rc and b releases, these will be built
        # out in the list comprehension below.
        # Finding the rc and b releases of the tag..
        if 'rc' not in tag and 'b' not in tag:
            rc_releases = [
                rc_tag for rc_tag in tags
                if tag in rc_tag and ('rc' in rc_tag or 'b' in rc_tag)
            ]
        new_list.extend(rc_releases)
        # Make sure we don't add the tag in twice
        if tag not in new_list:
            new_list.append(tag)
    return new_list


def run_osa_differ():
    """Start here."""
    # Get our arguments from the command line
    args = parse_arguments()

    # Set up DEBUG logging if needed
    if args.debug:
        log.setLevel(logging.DEBUG)
    elif args.verbose:
        log.setLevel(logging.INFO)

    # Create the storage directory if it doesn't exist already.
    try:
        storage_directory = prepare_storage_dir(args.directory)
    except OSError:
        print("ERROR: Couldn't create the storage directory {0}. "
              "Please create it manually.".format(args.directory))
        sys.exit(1)

    # Assemble some variables for the OSA repository.
    osa_old_commit = args.old_commit[0]
    osa_new_commit = args.new_commit[0]
    osa_repo_dir = "{0}/openstack-ansible".format(storage_directory)

    # Generate OpenStack-Ansible report header.
    report_rst = make_osa_report(osa_repo_dir,
                                 osa_old_commit,
                                 osa_new_commit,
                                 args)

    # Get OpenStack-Ansible Reno release notes for the packaged
    # releases between the two commits.
    if args.release_notes:
        report_rst += ("\nRelease Notes\n"
                       "-------------")
        report_rst += get_release_notes(osa_repo_dir,
                                        osa_old_commit,
                                        osa_new_commit)

    # Get the list of OpenStack roles from the newer and older commits.
    role_yaml = get_roles(osa_repo_dir,
                          osa_old_commit,
                          args.role_requirements)
    role_yaml_latest = get_roles(osa_repo_dir,
                                 osa_new_commit,
                                 args.role_requirements)

    if not args.skip_roles:
        # Generate the role report.
        report_rst += ("\nOpenStack-Ansible Roles\n"
                       "-----------------------")
        report_rst += make_report(storage_directory,
                                  role_yaml,
                                  role_yaml_latest,
                                  args.update)

    if not args.skip_projects:
        # Get the list of OpenStack projects from newer commit and older
        # commit.
        project_yaml = get_projects(osa_repo_dir, osa_old_commit)
        project_yaml_latest = get_projects(osa_repo_dir,
                                           osa_new_commit)

        # Generate the project report.
        report_rst += ("\nOpenStack Projects\n"
                       "------------------")
        report_rst += make_report(storage_directory,
                                  project_yaml,
                                  project_yaml_latest,
                                  args.update)

    # Publish report according to the user's request.
    output = publish_report(report_rst, args, osa_old_commit, osa_new_commit)
    print(output)


if __name__ == "__main__":
    run_osa_differ()
