# Tailscale plugin for StreamController

Control [Tailscale](https://tailscale.com) from your Stream Deck.

## Actions

| Action | What it does |
| --- | --- |
| **Connect** | `tailscale up` |
| **Disconnect** | `tailscale down` |
| **Toggle Connection** | Toggles up/down and shows live status — green when connected, grey when down, amber while connecting. |
| **Switch Account** | Toggles between two configured profiles (`tailscale switch`). Pick *Account A* and *Account B* in the button settings. |
| **Toggle Exit Node** | Toggles a configured exit node on/off (`tailscale set --exit-node=…`). Pick the node in the button settings. |

## Requirements

- StreamController **1.5.0-beta.14** or newer.
- The `tailscale` CLI installed on the host (the plugin reaches it from the
  flatpak sandbox via `flatpak-spawn --host`).
- **One-time setup so the plugin can control the daemon without `sudo`:**

  ```sh
  sudo tailscale set --operator=$USER
  ```

  Status reads work without this, but Connect/Disconnect/Toggle, account
  switching, and exit-node changes all require it. Until it is set, the
  Switch Account picker shows this command as a hint.

  **The operator setting is per-profile.** Each Tailscale account/profile you
  want to control stores its own operator pref, so you must run the command
  *once per account*: switch to each account, then run
  `sudo tailscale set --operator=$USER`. If you only set it on one profile,
  switching to another account will succeed but then every subsequent command
  (including switching back) is denied until that profile also has an operator.

## How it works

The plugin shells out to the host `tailscale` CLI. It does **not** use the
Tailscale cloud API (no API key needed). Status is read from
`tailscale status --json` and cached for ~2 seconds, shared across all
buttons, so the daemon is polled at most ~once every couple of seconds no
matter how many Tailscale buttons you have. Mutating commands run on a
background thread so the deck never freezes while `tailscale up` negotiates.

## Notes

- Switching to a profile whose login has expired may open a browser for
  re-authentication; log in to each profile from the host at least once.
- Exit-node candidates are discovered from your tailnet automatically (any
  peer advertising itself as an exit node).
