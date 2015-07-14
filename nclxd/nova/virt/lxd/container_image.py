# Copyright 2015 Canonical Ltd
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import hashlib
import os

from nova import exception
from nova import i18n
from nova import image
from nova.openstack.common import fileutils
from oslo_config import cfg
from oslo_log import log as logging
from pylxd import api
from pylxd import exceptions as lxd_exceptions

from nclxd.nova.virt.lxd import container_utils

_ = i18n._

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
IMAGE_API = image.API()


class LXDContainerImage(object):

    def __init__(self):
        self.lxd = api.API()
        self.container_dir = container_utils.LXDContainerDirectories()

    def fetch_image(self, context, instance, image_meta):
        LOG.debug("Downloading image file data %(image_ref)s to LXD",
                  {'image_ref': instance.image_ref})

        image_name = image_meta.get('name')
        if image_name in self.lxd.alias_list():
            return

        base_dir = self.container_dir.get_base_dir()
        if not os.path.exists(base_dir):
            fileutils.ensure_tree(base_dir)

        container_image = self.container_dir.get_container_image(image_meta)
        if os.path.exists(container_image):
            return

        IMAGE_API.download(context, instance.image_ref,
                           dest_path=container_image)

        ''' Upload the image to LXD '''
        with fileutils.remove_path_on_error(container_image):
            if self.lxd.image_defined(instance.image_ref):
                raise exception.ImageUnacceptable(
                    image_id=instance.image_ref,
                    reason=_('Image already exists.'))

            try:
                LOG.debug('Uploading image: %s' % container_image)
                self.lxd.image_upload(path=container_image)
            except lxd_exceptions.APIError as e:
                raise exception.ImageUnacceptable(
                    image_id=instance.image_ref,
                    reason=_('Image failed to upload: %s') % e)

            try:
                alias_config = {
                    'name': image_name,
                    'target': self.get_container_image_md5(image_meta)
                }
                LOG.debug('Creating alias: %s' % alias_config)
                self.lxd.alias_create(alias_config)
            except lxd_exceptions.APIError:
                raise exception.ImageUnacceptable(
                    image_id=instance.image_ref,
                    reason=_('Image already exists.'))

    def get_container_image_md5(self, image_meta):
        container_image = self.container_dir.get_container_image(image_meta)
        with open(container_image, 'rb') as fd:
            return hashlib.sha256(fd.read()).hexdigest()
