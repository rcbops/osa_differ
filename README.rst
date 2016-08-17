osa-differ
==========

Find changes between OpenStack-Ansible releases.

Background
----------

OpenStack-Ansible pins various OpenStack services and OpenStack-Ansible roles
to certain versions.  When these versions are updated, this is commonly called
a "SHA bump".  These updates involve changes to OpenStack-Ansible's main
repository, changes to individual OpenStack services (such as ``nova`` or
``glance``), and changes to OpenStack-Ansible roles (such as ``openstack-
ansible-os_nova``).

Following along with all of these changes can get complicated, and it can be a
challenge for deployers who want to know if a particular OpenStack-Ansible
version contains an important fix for an OpenStack service.

The ``osa-differ`` script has a goal of making this process easier.  The script
takes two OpenStack-Ansible commits and finds differences between them.

Installation
------------

The easiest method is to install via pip:

.. code-block:: console

   pip install osa_differ

To get the latest development version, install via the git repository:

.. code-block:: console

   pip install git+https://github.com/major/osa_differ

Usage
-----

Start by using ``--help`` to review all of the available options:

.. code-block:: console

   $ osa-differ --help
   usage: osa-differ

   OpenStack-Ansible Release Diff Generator
   ----------------------------------------

   Finds changes in OpenStack projects and OpenStack-Ansible roles between two
   commits in OpenStack-Ansible.

   positional arguments:
     old_commit            Git SHA of the older commit
     new_commit            Git SHA of the newer commit

   optional arguments:
     -h, --help            show this help message and exit
     --debug               Enable debug output
     -d DIRECTORY, --directory DIRECTORY
                           Git repo storage directory (default: ~/.osa-differ)
     -u, --update          Fetch latest changes to repo

   Limit scope:
     --skip-projects       Skip checking for changes in OpenStack projects
     --skip-roles          Skip checking for changes in OpenStack-Ansible roles

   Output options:
     Note: Output is always printed to stdout unless --quiet is provided.

     --quiet               Do not output to stdout
     --gist                Output into a GitHub Gist
     --file FILENAME       Output to a file

   Licensed "Apache 2.0"

The only required arguments are the commits you want to compare.  Always
provide the older commit first, followed by the newer commit:

.. code-block:: console

   # Compare changes from tags 13.3.0 to 13.3.1
   osa-differ 13.3.0 13.3.1

   # Compare changes between two specific commits
   osa-differ 876b25a 94c1ba3

If you get the commits in the wrong order, don't worry. The script checks for
that and will flip the order if it makes more sense.

By default, RestructuredText (RST) output is displayed on-screen for easy
copy-paste.  However, you can disable stdout output with ``--quiet`` and choose
a different option for output, such as a GitHub Gist or file.

Running tests
-------------

Simply run ``tox``:

.. code-block:: console

   # If you're in a hurry and want to test Python 2.7 only
   tox -e py27

   # Run all available tests
   tox

Found a bug? Have a pull request?
---------------------------------

Feel free to open issues here in GitHub or send over a pull request.
