#
# Copyright 2019 - Swiss Data Science Center (SDSC)
# A partnership between École Polytechnique Fédérale de Lausanne (EPFL) and
# Eidgenössische Technische Hochschule Zürich (ETHZ).
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
"""Tests for authentication functions."""

import pytest
import requests


@pytest.mark.parametrize("invalid_headers", [{}, {"Authorization": "token 8f7e09b3"}])
def test_unauthorized_access_returns_401(invalid_headers, base_url):
    response = requests.get(f"{base_url}/servers", headers=invalid_headers)
    assert response.status_code == 401


def test_authorized_access_works(headers, base_url):
    response = requests.get(f"{base_url}/servers", headers=headers)
    assert response.status_code == 200
