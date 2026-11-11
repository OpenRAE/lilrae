FROM debian:13@sha256:913f6706df59a68922d1dd08f78c2476560a8d367897200a6005b00e5f67c2d5

COPY containers/_wazuh-agent/install.sh /tmp/install-wazuh.sh
COPY containers/_wazuh-agent/aptl-firewall-drop.sh /tmp/aptl-firewall-drop.sh
COPY config/wazuh_cluster/etc/lists/active-response-whitelist /tmp/active-response-whitelist
COPY containers/_wazuh-agent/install-active-response.sh /tmp/install-active-response.sh
RUN /tmp/install-wazuh.sh && rm /tmp/install-wazuh.sh /tmp/aptl-firewall-drop.sh /tmp/active-response-whitelist /tmp/install-active-response.sh
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3-flask python3-gunicorn python3-psycopg2 python3-jwt iptables \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete
