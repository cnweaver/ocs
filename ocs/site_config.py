import ocs

import socket
import os
import yaml
    
class SiteConfig:
    def __init__(self):
        self.hosts = {}
        self.hub = None
        self.source_file = None

    @classmethod
    def from_dict(cls, data):
        """Args:
            data: The configuration dictionary.

        The configuration dictionary should have the following elements:

        ``hub`` (required): Describes what WAMP server and realm
            Agents and Clients should use.
        ``hosts`` (required): A dictionary of HostConfig
            descriptions.  The keys in this dictionary can be real
            host names on the network, or pseudo-host names if needed.

        """
        self = cls()
        for k,v in data.get('hosts', {}).items():
            assert (k not in self.hosts) # duplicate host name in config file!
            self.hosts[k] = HostConfig.from_dict(v, parent=self, name=k)
        self.hub = HubConfig.from_dict(data['hub'], parent=self)
        return self
        
    @classmethod
    def from_yaml(cls, filename):
        filename = os.path.abspath(filename)
        with open(filename) as f:
            data = yaml.safe_load(f)
        self = cls.from_dict(data)
        self.source_file = filename
        return self

class HostConfig:
    def __init__(self, name=None):
        self.instances = []
        self.name = name
        self.agent_paths = []
 
    @classmethod
    def from_dict(cls, data, parent=None, name=None):
        """Args:
            data: The configuration dictionary.
            parent: the SiteConfig from which this data was extracted
                (this is stored as self.parent, but not used).

        The configuration dictionary should have the following elements:
       
        ``agent-instances`` (required): A list of AgentConfig
            descriptions.

        ``agent-paths`` (optional): A list of additional paths where
            OCS is permitted to search for Agent plugin modules.

        """
        self = cls(name=name)
        self.parent = parent
        self.data = data
        self.instances = data['agent-instances']
        self.agent_paths = data.get('agent-paths', [])
        return self

class HubConfig:
    @classmethod
    def from_dict(cls, data, parent=None):
        """Args:
            data: The configuration dictionary.
            parent: the SiteConfig from which this data was extracted
                (this is stored as self.parent, but not used).

        The configuration dictionary should have the following elements:

        ``wamp_server`` (required): URL to the WAMP router's websocket
            access point for ocs.  E.g., ``ws://host-2:8001/ws``.
            WAMP routers can have multiple access points, with
            different protocols, security layers, and permissions.
            (Command line override: ``--site-hub``.)

        ``wamp_realm`` (required): The WAMP realm to use.  WAMP
            clients operating in a particular realm are isolated from
            clients connected to other realms.  Example and test code
            will often use ``debug_realm`` here.  (Command line
            override: ``--site-realm``.)

        ``address_root`` (required): The base address to be used by
            all OCS Agents.  This is normally something simple like
            ``observatory`` or ``detlab.system1``.  (Command line
            override: ``--address-root``.)

        ``registry_agent`` (optional): The address of the OCS Registry
            Agent.  See :ref:`registry`.  (Command line override:
            ``--registry-agent``.)

        """
        self = cls()
        self.parent = parent
        self.data = data
        return self

class InstanceConfig:
    def __init__(self):
        self.arguments = []

    @classmethod
    def from_dict(cls, data, parent=None):
        """Args:
            data: The configuration dictionary.
            parent: the HostConfig from which this data was extracted
                (this is stored as self.parent, but not used).

        The configuration dictionary should have the following elements:
       
        ``instance-id`` (str, required)
            This string is used to set the Agent instance's base
            address.  This may also be matched against the instance-id
            provided by the Agent instance, as a way of finding the
            right InstanceConfig.

        ``agent-class`` (str, optional)
            Name of the Agent class.  This
            may be matched against the agent_class name provided by
            the Agent instance, as a way of finding the right
            InstanceConfig.

        ``arguments`` (list, optional):
            A list of arguments that should be passed back to the
            agent.  Each element of the list should be a pair of
            strings, like ``['--option-name', 'value']``.  This is not
            as general as one might like, but is required in the
            current scheme.

        """
        self = cls()
        self.parent = parent
        self.data = data
        self.arguments = self.data['arguments']
        return self

    
    
def add_arguments(parser=None):
    """
    Add OCS site_config options to an ArgumentParser.

    Args:
        parser: an ArgumentParser.  If this is None, a new parser is
            created.

    Returns:
        The ArgumentParser that was passed in, or the new one.

    Arguments include the ``--site-*`` family.  See code or online
    documentation for details.
    """
    # Note that we use sphinxarg.ext to expose the help=... text in
    # the online sphinx docs.

    """
    ``--site=...``
        Instead of the default site, use the configuration
        for the specified site.  The configuration is loaded from
        ``$OCS_CONFIG_DIR/{site}.yaml``.  If --site=none, the
        site_config facility will not be used at all.

    ``--site-file=...``
        Instead of the default site config, use the
        specified file.  Full path must be specified.

    ``--site-host=...``
        Override the OCS determination of what host this instance is
        running on, and instead use the configuration for the
        indicated host.

    ``--site-hub=...``:
        Override the ocs hub url (wamp_server).

    ``--site-realm=...``:
        Override the ocs hub realm (wamp_realm).

    ``--instance-id=...``:
        Look in the SCF for Agent-instance specific configuration
        options, and use those to launch the Agent.

    ``--address-root=...``:
        Override the site default address root.

    """
    if parser is None:
        import argparse
        parser = argparse.ArgumentParser()
    group = parser.add_argument_group('Site Config Options')
    group.add_argument('--site', help=
    """Instead of the default site, use the configuration for the
       specified site.  The configuration is loaded from
       ``$OCS_CONFIG_DIR/{site}.yaml``.  If ``--site=none``, the
       site_config facility will not be used at all.""")
    group.add_argument('--site-file', help=
    """Instead of the default site config, use the specified file.  Full
       path must be specified.""")
    group.add_argument('--site-host', help=
    """Override the OCS determination of what host this instance is
       running on, and instead use the configuration for the indicated
       host.""")
    group.add_argument('--site-hub', help=
    """Override the ocs hub url (wamp_server).""")
    group.add_argument('--site-realm', help=
    """Override the ocs hub realm (wamp_realm).""")
    group.add_argument('--instance-id', help=
    """Look in the SCF for Agent-instance specific configuration options,
       and use those to launch the Agent.""")
    group.add_argument('--address-root', help=
    """Override the site default address root.""")
    group.add_argument('--registry-address', help=
    """Override the site default registry address.""")
    return parser
    
def get_config(args, agent_class=None):
    """
    Args:
        args: The argument object returned by
            ArgumentParser.parse_args(), or equivalent.  It is assumed
            that all properties defined by "add_arguments" are present
            in this object.
        agent_class: Class name passed in to match against the list of
            device classes in each host's list.

    Special values accepted for agent_class:
    - '*control*': do not insist on matching host or device.
    - '*host*': do not insist on matching device (but do match host).

    Returns:
        The tuple (site_config, host_config, device_config).
    """
    if args.site == 'none':
        return (None,None,None)
    
    site_file = args.site_file
    site = args.site
    if site_file is None:
        if site is None:
            site = 'default'
        assert (os.getenv('OCS_CONFIG_DIR') is not None)
        site_file = os.path.join(os.getenv('OCS_CONFIG_DIR'),
                                 site + '.yaml')
    else:
        assert (site is None) # do not pass both --site and --site-file

    # Load the site config file.
    site_config = SiteConfig.from_yaml(site_file)

    # Override the WAMP hub?
    if args.site_hub is not None:
        site_config.hub.data['wamp_server'] = args.site_hub

    # Override the realm?
    if args.site_realm is not None:
        site_config.hub.data['wamp_realm'] = args.site_realm

    if args.registry_address is not None:
        site_config.hub.data['registry_address'] = args.registry_address

    # Matching behavior.
    no_host_match = (agent_class == '*control*')
    no_dev_match = no_host_match or (agent_class == '*host*')

    # Identify our host.
    host = args.site_host
    if host is None:
        host = socket.gethostname()

    if no_host_match:
        host_config = None
    else:
        host_config = site_config.hosts[host]

    # Identify our agent-instance.
    instance_config = None
    if no_dev_match:
        pass
    elif args.instance_id is not None:
        # Find the config for this instance-id.
        for dev in host_config.instances:
            if dev['instance-id'] == args.instance_id:
                instance_config = InstanceConfig.from_dict(
                    dev, parent=host_config)
                break
    else:
        # Use the agent_class to figure it out...
        matches = 0
        for dev in host_config.instances:
            if dev['agent-class'] == agent_class:
                if instance_config is not None:
                    raise RuntimeError("Multiple matches found for "
                                       "agent-class=%s" % agent_class)
                instance_config = InstanceConfig.from_dict(
                    dev, parent=host_config)
    if instance_config is None and not no_dev_match:
        raise RuntimeError("Could not find matching device description.")

    return (site_config, host_config, instance_config)

def reparse_args(args, agent_class=None):
    """
    Process the site-config arguments, and modify them in place
    according to the agent-instance's computed instance-id.

    Args:
        args: The argument object returned by
            ArgumentParser.parse_args(), or equivalent.

        agent_class: Class name passed in to match against the list of
            device classes in each host's list.

    Special values accepted for agent_class:
    - '*control*': do not insist on matching host or device.
    """
    if args.site=='none':
        return args

    site, host, instance = get_config(args, agent_class=agent_class)

    if args.site_hub is None:
        args.site_hub = site.hub.data['wamp_server']
    if args.site_realm is None:
        args.site_realm = site.hub.data['wamp_realm']
    if args.address_root is None:
        args.address_root = site.hub.data['address_root']
    if args.registry_address is None:
        args.registry_address = site.hub.data.get('registry_address')

    if instance is not None:
        if args.instance_id is None:
            args.instance_id = instance.data['instance-id']

        for k,v in instance.data['arguments']:
            kprop = k.lstrip('-').replace('-','_')
            print('site_config is setting values of "%s" to "%s".' % (kprop, v))
            setattr(args, kprop, v)

    return args


# We'll also keep the Agent script registry here.
agent_script_reg = {}

def register_agent_class(class_name, filename):
    """Register an Agent script in the site_config registry.

    Args:
        class_name (str): The Agent class name, e.g. "HostManager".
        filename (str): The full path to the script that launches an
            instance of this Agent class.

    """
    agent_script_reg[class_name] = filename

def scan_for_agents(do_registration=True):
    """Identify and import ocs Agent plugin scripts.  This will find all
    modules in the current module search path (sys.path) that begin
    with the name 'ocs_plugin_'.

    Args:
        do_registration (bool): If True, the modules are imported,
            which likely causes them to call register_agent_class on
            each agent they represent.

    Returns:
        The list of discovered module names.

    """
    import pkgutil
    import importlib
    items = []
    for modinfo in pkgutil.iter_modules():
        if modinfo.name.startswith('ocs_plugin_'):
            items.append(modinfo.name)
            if do_registration:
                importlib.import_module(modinfo.name)
    return items
                    
