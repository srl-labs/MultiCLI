# Custom CLI Plugins for Extreme SLX

The following CLI plugins are available in this repo:

> [!NOTE]
> At the time of releasing these scripts, SR Linux did not support a custom CLI path that was loaded on top of an existing native path. Due to this reason, some SLX commands start with the syntax `show slx`. This will be fixed in a future release.

| Command |
|---|---|
| `show slx interface` |


## Testing

Deploy the EVPN lab. Login to any leaf or spine node using `exuser/exuser` and try any of the above commands.

## Custom CLI Plugin scripts

This folder contains custom CLI python scripts for SLX commands.

The scripts are arranged in this format. The main_extreme.py checks the imports in the shown path below

```
/home/auser/cli
│
├── interface
│   ├── extreme_interface_detail.py   # Displays detailed interface info (Extreme style)
│   
└── plugins
    ├── main_extreme.py               # Loads Extreme-style CLI plugins

```

### Verification commands:

**Interface Details**:
```
show slx interface {interface_name}
```
*OR, to list all interfaces*

```
show slx interface
```

## Notes
- Queueing strategy only displays fifo which seems to be in line with SLX documentation
- Overruns there is no equivalent mentric in srlinux
- MaximumSpeed, LineSpeed Actual and LineSpeed configure are all set to what is returned by `/interface[name=*]/ethernet/port-speed`