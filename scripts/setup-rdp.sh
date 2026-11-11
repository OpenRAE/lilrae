#!/bin/bash
# =============================================================================
# setup-rdp.sh -- add RDP access + a light desktop to an APTL Arsenal range.
# =============================================================================
# Participants RDP into the range host and drive the demo from there: a terminal
# for Claude Code (the MCP agent) and Firefox for the Wazuh / SOC web UIs. Run
# once on the box before baking the AMI so every clone has RDP on :3389.
#
# The RDP password for the `ubuntu` user is set here; override with APTL_RDP_PASS.
# Distribute it alongside the per-range .rdp files.
# =============================================================================
set -uo pipefail

RDP_USER="${APTL_RDP_USER:-ubuntu}"
RDP_PASS="${APTL_RDP_PASS:-AptlArsenal!2026}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_DIR="${APTL_PROJECT_DIR:-/home/$RDP_USER/aptl3}"

echo "=== setup-rdp starting $(date -u) ==="
export DEBIAN_FRONTEND=noninteractive
# Wait up to 10 min for the dpkg lock (Ubuntu's unattended-upgrades holds it on a
# fresh boot) instead of failing immediately.
APT=(sudo -E apt-get -o DPkg::Lock::Timeout=600 -y)
"${APT[@]}" update >/tmp/rdp-apt.log 2>&1
# xfce4 (light desktop) + xfce4-terminal + xrdp + dbus-x11 for the session.
"${APT[@]}" install xrdp xorgxrdp xfce4 xfce4-terminal dbus-x11 >>/tmp/rdp-apt.log 2>&1
# Browser for the SOC web UIs. Use the NATIVE epiphany-browser .deb, not the
# Firefox snap: snap apps take 30-60s+ to first-launch from squashfs in an xrdp
# session (reads as "the box is frozen"). Native = instant.
"${APT[@]}" install epiphany-browser >>/tmp/rdp-apt.log 2>&1 || true

# xfce pulls in avahi-daemon (mDNS). The workshop does not need it -- mask it.
sudo systemctl disable --now avahi-daemon.service avahi-daemon.socket 2>/dev/null || true
sudo systemctl mask avahi-daemon.service avahi-daemon.socket 2>/dev/null || true

# Session: xfce for the RDP user.
echo "xfce4-session" | sudo tee "/home/$RDP_USER/.xsession" >/dev/null
sudo chown "$RDP_USER:$RDP_USER" "/home/$RDP_USER/.xsession"
# System-wide default so xrdp's Xorg session starts xfce even without ~/.xsession.
sudo tee /etc/xrdp/startwm.sh >/dev/null <<'WM'
#!/bin/sh
if [ -r /etc/profile ]; then . /etc/profile; fi
if [ -r "$HOME/.profile" ]; then . "$HOME/.profile"; fi
exec /usr/bin/startxfce4
WM
sudo chmod +x /etc/xrdp/startwm.sh

# xrdp user must read the TLS key it generates.
sudo adduser xrdp ssl-cert >/dev/null 2>&1 || true

# Set the RDP login password for the participant user.
echo "$RDP_USER:$RDP_PASS" | sudo chpasswd

# A desktop launcher so participants see how to start the agent immediately.
sudo -u "$RDP_USER" mkdir -p "/home/$RDP_USER/Desktop"
sudo -u "$RDP_USER" tee "/home/$RDP_USER/Desktop/Start-Claude-Agent.desktop" >/dev/null <<'DESK'
[Desktop Entry]
Version=1.0
Type=Application
Name=Start Claude Agent
Comment=Open a terminal in the aptl repo and launch Claude Code
Exec=xfce4-terminal --working-directory=/home/ubuntu/aptl3 -e "bash -lc 'echo Run: claude ; exec bash'"
Icon=utilities-terminal
Terminal=false
DESK
sudo chmod +x "/home/$RDP_USER/Desktop/Start-Claude-Agent.desktop" 2>/dev/null || true
sudo chown -R "$RDP_USER:$RDP_USER" "/home/$RDP_USER/Desktop"

# Participant desktop (issue #1273). Lab start runs as the RDP user with
# LILRAE_PARTICIPANT_DESKTOP_ACCOUNT set (scripts/aptl-range.service), so it
# writes that user's private desktop files and a non-secret hosts.json. The
# shared publisher, installed root-owned, applies the hostnames after the range
# service; the opener shows the logins, guide, and consoles at session start.
sudo install -D -m 0755 -o root -g root "$REPO_DIR/src/aptl/core/participant_hosts.py" \
    /usr/local/libexec/lilrae-participant-hosts
sudo install -D -m 0755 -o root -g root "$REPO_DIR/appliance/guest/participant-desktop-open.sh" \
    /usr/local/bin/lilrae-participant-desktop-open
RANGE_OWNER="$(stat -c %U "$PROJECT_DIR")"
sudo tee /etc/systemd/system/lilrae-participant-hosts.service >/dev/null <<UNIT
[Unit]
Description=Publish the participant desktop hostnames that lab start resolved
After=aptl-range.service
Requires=aptl-range.service
PartOf=aptl-range.service

[Service]
Type=oneshot
RemainAfterExit=yes
# The range service runs as this administrator; the root-owned unit explicitly
# selects whose management document it trusts, independently of the ready marker.
ExecStart=/usr/bin/python3 /usr/local/libexec/lilrae-participant-hosts --document-owner $RANGE_OWNER $PROJECT_DIR/.aptl/participant-desktop/hosts.json
ExecStop=/usr/bin/python3 /usr/local/libexec/lilrae-participant-hosts --clear

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl enable lilrae-participant-hosts.service >/dev/null 2>&1
sudo -u "$RDP_USER" mkdir -p "/home/$RDP_USER/.config/autostart"
sudo -u "$RDP_USER" tee "/home/$RDP_USER/.config/autostart/lilrae-participant-desktop.desktop" >/dev/null <<DESK
[Desktop Entry]
Type=Application
Name=Lab consoles
Exec=/usr/local/bin/lilrae-participant-desktop-open --wait-for-range /home/$RDP_USER/.config/aptl/desktop
Terminal=false
DESK

# Responsiveness over internet RDP: 32bpp at 1080p with the xfce compositor is
# heavy and reads as "the box is slow" even when it is idle. Cap to 16bpp and
# disable compositing -- the single biggest lag win.
sudo sed -i 's/^max_bpp=.*/max_bpp=16/' /etc/xrdp/xrdp.ini
# xrdp's default TCP send/recv buffers are 32KB, which starves throughput and is
# the top-reported cause of laggy window dragging over anything but a fast LAN
# (neutrinolabs/xrdp #1483/#2135/#2393). Bump to 4MB.
if ! grep -q '^tcp_send_buffer_bytes' /etc/xrdp/xrdp.ini; then
    sudo sed -i '/^tcp_nodelay=true/a tcp_send_buffer_bytes=4194304\ntcp_recv_buffer_bytes=4194304' /etc/xrdp/xrdp.ini
fi
sudo -u "$RDP_USER" mkdir -p "/home/$RDP_USER/.config/xfce4/xfconf/xfce-perchannel-xml"
sudo -u "$RDP_USER" tee "/home/$RDP_USER/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml" >/dev/null <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="use_compositing" type="bool" value="false"/>
  </property>
</channel>
XML

sudo systemctl enable xrdp >/dev/null 2>&1
sudo systemctl restart xrdp

sleep 2
if ss -tlnp 2>/dev/null | grep -q ':3389'; then
    echo "RDP_READY :3389 user=$RDP_USER"
else
    echo "RDP_SETUP_FAILED -- see /tmp/rdp-apt.log"
fi
echo "=== setup-rdp done $(date -u) ==="
