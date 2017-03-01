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
import os
import sys


from git import Repo
import jinja2
import requests
import yaml
from . import exceptions


def create_parser():
    """Setup argument Parsing."""
    description = """OpenStack-Ansible Release Diff Generator
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
        '-u', '--update',
        action='store_true',
        default=False,
        help="Fetch latest changes to repo",
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
        return repo_url
    if "git.openstack.org" in repo_url:
        uri = '/'.join(repo_url.split('/')[-2:])
        return "https://github.com/{0}".format(uri)

    # If it didn't match these conditions, just return it.
    return repo_url


def get_projects(osa_repo_dir, commit):
    """Get all projects from multiple YAML files."""
    # Check out the correct commit SHA from the repository
    repo = Repo(osa_repo_dir)
    repo.head.reference = repo.commit(commit)
    repo.head.reset(index=True, working_tree=True)

    yaml_files = glob.glob(
        '{0}/playbooks/defaults/repo_packages/*.yml'.format(osa_repo_dir)
    )
    yaml_parsed = []
    for yaml_file in yaml_files:
        with open(yaml_file, 'r') as f:
            yaml_parsed.append(yaml.load(f))

    merged_dicts = {k: v for d in yaml_parsed for k, v in d.items()}

    return normalize_yaml(merged_dicts)


def get_roles(osa_repo_dir, commit):
    """Read OSA role information at a particular commit."""
    repo = Repo(osa_repo_dir)
    repo.head.reference = repo.commit(commit)
    repo.head.reset(index=True, working_tree=True)

    filename = "{0}/ansible-role-requirements.yml".format(osa_repo_dir)
    with open(filename, 'r') as f:
        roles_yaml = yaml.load(f)

    return normalize_yaml(roles_yaml)


def make_osa_report(repo_dir, old_commit, new_commit,
                    args):
    """Create initial RST report header for OpenStack-Ansible."""
    osa_repo_url = "https://git.openstack.org/openstack/openstack-ansible"
    update_repo(repo_dir, osa_repo_url, args.update)

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
        'commit_base_url': get_commit_url(osa_repo_url),
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
        except:
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
    repo.heads.master.checkout()
    repo.head.reset(index=True, working_tree=True)

    # Only get the latest updates if requested.
    if fetch:
        repo.remotes['origin'].pull()

    return repo


def update_repo(repo_dir, repo_url, fetch=False):
    """Clone the repo if it doesn't exist already, otherwise update it."""
    repo_exists = os.path.exists(repo_dir)
    if repo_exists:
        repo = repo_pull(repo_dir, repo_url, fetch)
    else:
        repo = repo_clone(repo_dir, repo_url)

    return repo


def validate_commits(repo_dir, commits):
    """Test if a commit is valid for the repository."""
    repo = Repo(repo_dir)
    for commit in commits:
        try:
            commit = repo.commit(commit)
        except:
            msg = ("Commit {0} could not be found. You may need to pass "
                   "--update to fetch the latest updates to the git "
                   "repositories stored on you local computer.".format(commit))
            raise exceptions.InvalidCommitException(msg)

    return True


def validate_commit_range(repo_dir, old_commit, new_commit):
    """Check if commit range is valid. Flip it if needed."""
    # Are there any commits between the two commits that were provided?
    try:
        commits = get_commits(repo_dir, old_commit, new_commit)
    except:
        commits = []
    if len(commits) == 0:
        # The user might have gotten their commits out of order. Let's flip
        # the order of the commits and try again.
        try:
            commits = get_commits(repo_dir, new_commit, old_commit)
        except:
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


def run_osa_differ():
    """The script starts here."""
    # Get our arguments from the command line
    args = parse_arguments()

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

    # Get the list of OpenStack roles from the newer and older commits.
    role_yaml = get_roles(osa_repo_dir, osa_old_commit)
    role_yaml_latest = get_roles(osa_repo_dir, osa_new_commit)

    # Generate the role report.
    report_rst += ("\nOpenStack-Ansible Roles\n"
                   "-----------------------")
    report_rst += make_report(storage_directory,
                              role_yaml,
                              role_yaml_latest,
                              args.update)

    # Get the list of OpenStack projects from newer commit and older commit.
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
