# Troubleshooting

## Micro-Manager directory not found

```sh
pymmcore-plus - ERROR - (_util.py:131) could not find micromanager directory. Please run 'mmcore install'
```

If you tried to create a [`pymmcore_plus.CMMCorePlus`](api/cmmcoreplus.md) instance and got an
error similar the one above, it means that pymmcore-plus was unable to find micro-manager on on your system.
(for example, you can run `mmcore install` to install the latest version of Micro-Manager).

See the [installation](install.md#installing-micro-manager-device-adapters) section for more details.

## Incompatible device interface version

```sh
OSError: Line 7: Device,DHub,DemoCamera,DHub
Failed to load device "DHub" from adapter module "DemoCamera" [ Failed to load device adapter "DemoCamera" from "/Users/fdrgsp/Library/Application Support/pymmcore-plus/mm/Micro-Manager-2.0.1-20210715/libmmgr_dal_DemoCamera" [ Incompatible device interface version (required = 71; found = 70) ] ]
```

If you create a [`pymmcore_plus.CMMCorePlus`](api/cmmcoreplus.md) instance and you get an error similar the one above when trying to load a Micro-Manager configuration file, you need to **update** your Micro-Manager device adapters installation to the newest version (for example by running: `mmcore install`).

See the [installation](install.md#installing-micro-manager-device-adapters) section for more details.
