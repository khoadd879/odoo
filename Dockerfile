FROM odoo:18.0

USER root

# Ensure git, gosu, and envsubst are available
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates gosu gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Copy Odoo config and entrypoint
COPY odoo.conf /etc/odoo/odoo.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && chown odoo:odoo /etc/odoo/odoo.conf

# Ensure Odoo user owns its data dir
RUN mkdir -p /var/lib/odoo \
    && chown -R odoo:odoo /var/lib/odoo

USER root

EXPOSE 8069 8072

ENTRYPOINT ["/entrypoint.sh"]
