import pprint
from typing import Any, Dict
from unittest.mock import patch
import requests
import os
from marqo.tensor_search.models.add_docs_objects import AddDocsParams
from marqo.tensor_search.enums import IndexSettingsField, EnvVars
from marqo.errors import MarqoApiError, MarqoError, IndexNotFoundError
from marqo.tensor_search import tensor_search, configs, backend, create_index
from marqo.tensor_search.utils import read_env_vars_and_defaults
from tests.marqo_test import MarqoTestCase
from marqo.tensor_search.enums import IndexSettingsField as NsField, TensorField
from unittest import mock
from marqo.tensor_search.models.settings_object import settings_schema
from marqo import errors
from marqo.errors import InvalidArgError

class TestCreateIndex(MarqoTestCase):

    def setUp(self, custom_index_defaults: Dict[str, Any] = {}) -> None:
        self.endpoint = self.authorized_url
        self.generic_header = {"Content-type": "application/json"}
        self.index_name_1 = "my-test-create-index-1"
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError as s:
            pass

        # Any tests that call add_documents, search, bulk_search need this env var
        self.device_patcher = mock.patch.dict(os.environ, {"MARQO_BEST_AVAILABLE_DEVICE": "cpu"})
        self.device_patcher.start()

    def tearDown(self) -> None:
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError as s:
            pass
        self.device_patcher.stop()

    def test_create_vector_index_default_index_settings(self):
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError as s:
            pass
        # test that index is deleted:
        try:
            tensor_search.search(config=self.config, index_name=self.index_name_1, text="some text")
            raise AssertionError
        except IndexNotFoundError as e:
            pass
        tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1)
        settings = requests.get(
            url=f"{self.endpoint}/{self.index_name_1}/_mapping",
            verify=False
        ).json()

        default_index_settings = configs.get_default_index_settings()
        default_index_settings = create_index.autofill_search_model(default_index_settings)
        assert default_index_settings is not None
        
        assert settings[self.index_name_1]["mappings"]["_meta"][IndexSettingsField.index_settings] \
            == default_index_settings

    def test_create_vector_index__invalid_settings(self):
        custom_index_defaults = [
            {IndexSettingsField.ann_parameters: {
                    IndexSettingsField.ann_method: "fancy-new-ann-method",
            }},
            {IndexSettingsField.ann_parameters: {
                    IndexSettingsField.ann_method: "ivf",
            }},
            {IndexSettingsField.ann_parameters: {
                IndexSettingsField.ann_engine: "faiss",
            }},
            {IndexSettingsField.ann_parameters: {
                IndexSettingsField.ann_metric: "innerproduct",
            }},
            {IndexSettingsField.ann_parameters: {
                IndexSettingsField.ann_method_parameters: {
                IndexSettingsField.hnsw_ef_construction: 0,
                IndexSettingsField.hnsw_m: 16
            }}},
            {IndexSettingsField.ann_parameters: {
                IndexSettingsField.ann_method_parameters: {
                IndexSettingsField.hnsw_ef_construction: 128,
                IndexSettingsField.hnsw_m: 101
            }}},
            {IndexSettingsField.ann_parameters: {
                IndexSettingsField.ann_method_parameters: {
                IndexSettingsField.hnsw_ef_construction: 1 + int(read_env_vars_and_defaults(EnvVars.MARQO_EF_CONSTRUCTION_MAX_VALUE)),
                IndexSettingsField.hnsw_m: 16
            }}},
            {IndexSettingsField.ann_parameters: {IndexSettingsField.ann_method_parameters: {
                IndexSettingsField.hnsw_ef_construction: 128,
                IndexSettingsField.hnsw_m: -1
            }}},
        ]
        for idx_defaults in custom_index_defaults:
            with self.subTest(custom_index_defaults=idx_defaults):
                try:
                    tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
                except IndexNotFoundError as s:
                    pass
                
                with self.assertRaises(errors.InvalidArgError):
                    print(f"index settings={idx_defaults}")
                    tensor_search.create_vector_index(
                        config=self.config,
                        index_name=self.index_name_1,
                        index_settings={
                            NsField.index_defaults: idx_defaults
                        }
                    )
                    print(tensor_search.get_index_info(self.config, self.index_name_1))

    def test_create_vector_index_custom_index_settings(self):
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError as s:
            pass
        # test that index is deleted:
        try:
            tensor_search.search(config=self.config, index_name=self.index_name_1, text="some text")
            raise AssertionError
        except IndexNotFoundError as e:
            pass
        custom_settings = {
            IndexSettingsField.treat_urls_and_pointers_as_images: True,
            IndexSettingsField.normalize_embeddings: False
        }
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, index_settings={
                NsField.index_defaults: custom_settings})
        settings = requests.get(
            url=self.endpoint + "/" + self.index_name_1 + "/_mapping",
            verify=False
        ).json()
        pprint.pprint(settings)
        retrieved_settings = settings[self.index_name_1]["mappings"]["_meta"][IndexSettingsField.index_settings]
        del retrieved_settings[IndexSettingsField.index_defaults][IndexSettingsField.model]
        del retrieved_settings[IndexSettingsField.index_defaults][IndexSettingsField.search_model]

        default_settings = tensor_search.configs.get_default_index_settings()
        default_text_preprocessing = default_settings[IndexSettingsField.index_defaults][IndexSettingsField.text_preprocessing]
        default_image_preprocessing = default_settings[IndexSettingsField.index_defaults][IndexSettingsField.image_preprocessing]

        assert retrieved_settings == {
            IndexSettingsField.index_defaults: {
                IndexSettingsField.treat_urls_and_pointers_as_images: True,
                IndexSettingsField.normalize_embeddings: False,
                IndexSettingsField.text_preprocessing: default_text_preprocessing,
                IndexSettingsField.image_preprocessing: default_image_preprocessing,
                IndexSettingsField.ann_parameters: {
                    IndexSettingsField.ann_engine: 'lucene',
                    IndexSettingsField.ann_method_name: 'hnsw',
                    IndexSettingsField.ann_method_parameters: {
                        IndexSettingsField.hnsw_ef_construction: 128,
                        IndexSettingsField.hnsw_m: 16
                    },
                    IndexSettingsField.ann_metric: 'cosinesimil'
                },
            },
            IndexSettingsField.number_of_shards: default_settings[IndexSettingsField.number_of_shards],
            IndexSettingsField.number_of_replicas: default_settings[IndexSettingsField.number_of_replicas]
        }

    def test_create_vector_index_default_knn_settings(self):
        """Do the Marqo-OS settings correspond to the Marqo index settings? For default HNSW params"""
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError as s:
            pass
        # test that index is deleted:
        try:
            tensor_search.search(config=self.config, index_name=self.index_name_1, text="some text")
            raise AssertionError
        except IndexNotFoundError as e:
            pass
        custom_settings = {
            IndexSettingsField.treat_urls_and_pointers_as_images: True,
            IndexSettingsField.normalize_embeddings: False
        }
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, index_settings={
                NsField.index_defaults: custom_settings})
        tensor_search.add_documents(
            config=self.config, add_docs_params=AddDocsParams(
                index_name=self.index_name_1, docs=[{"Title": "wowow"}], auto_refresh=True, device="cpu"))
        mappings = requests.get(
            url=self.endpoint + "/" + self.index_name_1 + "/_mapping",
            verify=False
        ).json()
        params = mappings[self.index_name_1]['mappings']['properties']['__chunks']['properties'][TensorField.marqo_knn_field]['method']
        assert params['engine'] == 'lucene'
        assert params['space_type'] == 'cosinesimil'
        assert params['parameters'] == {'ef_construction': 128, 'm': 16}

    def test_create_vector_index_custom_knn_settings(self):
        """Do the Marqo-OS settings correspond to the Marqo index settings? For custom HNSW params"""
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError as s:
            pass
        # test that index is deleted:
        try:
            tensor_search.search(config=self.config, index_name=self.index_name_1, text="some text")
            raise AssertionError
        except IndexNotFoundError as e:
            pass
        custom_settings = {
            IndexSettingsField.treat_urls_and_pointers_as_images: True,
            IndexSettingsField.normalize_embeddings: False,
            IndexSettingsField.ann_parameters: {
                IndexSettingsField.ann_metric: "l2",
                IndexSettingsField.ann_method_parameters: {
                    IndexSettingsField.hnsw_m: 17,
                    IndexSettingsField.hnsw_ef_construction: 133,
                }
            }
        }
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, index_settings={
                NsField.index_defaults: custom_settings})
        tensor_search.add_documents(
            config=self.config, add_docs_params=AddDocsParams(
                index_name=self.index_name_1, docs=[{"Title": "wowow"}], auto_refresh=True, device="cpu"))
        mappings = requests.get(
            url=self.endpoint + "/" + self.index_name_1 + "/_mapping",
            verify=False
        ).json()
        params = mappings[self.index_name_1]['mappings']['properties']['__chunks']['properties'][TensorField.marqo_knn_field]['method']
        assert params['engine'] == 'lucene'
        assert params['space_type'] == 'l2'
        assert params['parameters'] == {'ef_construction': 133, 'm': 17}

    def test__autofill_index_settings_fill_missing_text_preprocessing(self):
        modified_settings = tensor_search.configs.get_default_index_settings()
        del modified_settings[IndexSettingsField.index_defaults][IndexSettingsField.text_preprocessing]\
            [IndexSettingsField.split_method]
        assert IndexSettingsField.split_method not in \
               modified_settings[IndexSettingsField.index_defaults][IndexSettingsField.text_preprocessing]
        del modified_settings[IndexSettingsField.index_defaults][IndexSettingsField.text_preprocessing]\
            [IndexSettingsField.override_text_chunk_prefix]
        assert IndexSettingsField.override_text_chunk_prefix not in \
               modified_settings[IndexSettingsField.index_defaults][IndexSettingsField.text_preprocessing]
        del modified_settings[IndexSettingsField.index_defaults][IndexSettingsField.text_preprocessing]\
            [IndexSettingsField.override_text_query_prefix]
        assert IndexSettingsField.override_text_query_prefix not in \
               modified_settings[IndexSettingsField.index_defaults][IndexSettingsField.text_preprocessing]
        assert tensor_search._autofill_index_settings(modified_settings) \
            == tensor_search.configs.get_default_index_settings()

    def test_default_number_of_shards(self):
        """does an index get created with the default number of shards?"""
        tensor_search.create_vector_index(index_name=self.index_name_1, config=self.config)
        default_shard_count = configs.get_default_index_settings()[NsField.number_of_shards]
        assert default_shard_count is not None
        resp = requests.get(
            url=self.authorized_url + f"/{self.index_name_1}",
            verify=False
        )
        assert default_shard_count == int(resp.json()[self.index_name_1]['settings']['index']['number_of_shards'])

    def test_autofill_number_of_shards(self):
        """ does it work if other params are filled?"""
        tensor_search.create_vector_index(
            index_name=self.index_name_1, config=self.config,
            index_settings={
                "index_defaults": {
                    "treat_urls_and_pointers_as_images": True,
                    "model": "ViT-B/32",
                }}
        )
        default_shard_count = configs.get_default_index_settings()[NsField.number_of_shards]
        assert default_shard_count is not None
        resp = requests.get(
            url=self.authorized_url + f"/{self.index_name_1}",
            headers=self.generic_header,
            verify=False
        )
        assert default_shard_count == int(resp.json()[self.index_name_1]['settings']['index']['number_of_shards'])

    def test_default_number_of_replicas(self):
        tensor_search.create_vector_index(index_name=self.index_name_1, config=self.config)
        default_replicas_count = configs.get_default_index_settings()[NsField.number_of_replicas]
        assert default_replicas_count is not None
        resp = requests.get(
            url=self.authorized_url + f"/{self.index_name_1}",
            verify=False
        )
        assert default_replicas_count == int(resp.json()[self.index_name_1]['settings']['index']['number_of_replicas'])

    def test_autofill_number_of_replicas(self):
        tensor_search.create_vector_index(
            index_name=self.index_name_1, config=self.config,
            index_settings={
                "index_defaults": {
                    "treat_urls_and_pointers_as_images": True,
                    "model": "ViT-B/32",
                }}
        )
        default_replicas_count = configs.get_default_index_settings()[NsField.number_of_replicas]
        assert default_replicas_count is not None
        resp = requests.get(
            url=self.authorized_url + f"/{self.index_name_1}",
            headers=self.generic_header,
            verify=False
        )
        assert default_replicas_count == int(resp.json()[self.index_name_1]['settings']['index']['number_of_replicas'])
    
    def test_autofill_index_defaults(self):
        """ Does autofill work as intended when index_defaults is not set, but number_of_shards is?"""
        intended_shard_count = 6
        tensor_search.create_vector_index(
            index_name=self.index_name_1, config=self.config,
            index_settings={
                NsField.number_of_shards: intended_shard_count        
            }
        )
        
        default_index_settings = configs.get_default_index_settings()
        default_index_settings = create_index.autofill_search_model(default_index_settings)
        assert default_index_settings is not None
        
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        test_index_defaults = index_info.index_settings[NsField.index_defaults]

        assert default_index_settings[NsField.index_defaults] == test_index_defaults

    def test_set_number_of_shards(self):
        """ does it work if other params are filled?"""
        intended_shard_count = 6
        res_0 = tensor_search.create_vector_index(
            index_name=self.index_name_1, config=self.config,
            index_settings={
                "index_defaults": {
                    "treat_urls_and_pointers_as_images": True,
                    "model": "ViT-B/32",
                },
                NsField.number_of_shards: intended_shard_count
            }
        )
        resp = requests.get(
            url=self.authorized_url + f"/{self.index_name_1}",
            headers=self.generic_header,
            verify=False
        )
        assert intended_shard_count == int(resp.json()[self.index_name_1]['settings']['index']['number_of_shards'])

    def test_set_number_of_replicas(self):
        intended_replicas_count = 4
        from marqo.tensor_search.models.settings_object import settings_schema
        with patch.dict(settings_schema["properties"][NsField.number_of_replicas], maximum=10):
            res_0 = tensor_search.create_vector_index(
                index_name=self.index_name_1, config=self.config,
                index_settings={
                    "index_defaults": {
                        "treat_urls_and_pointers_as_images": True,
                        "model": "ViT-B/32",
                    },
                    NsField.number_of_replicas: intended_replicas_count
                }
            )
        resp = requests.get(
            url=self.authorized_url + f"/{self.index_name_1}",
            headers=self.generic_header,
            verify=False
        )
        assert intended_replicas_count == int(resp.json()[self.index_name_1]['settings']['index']['number_of_replicas'])

    def test_configurable_max_number_of_replicas(self):
        maximum_number_of_replicas = 5
        large_intended_replicas_count = 10
        small_intended_replicas_count = 3
        from marqo.tensor_search.models.settings_object import settings_schema

        with patch.dict(settings_schema["properties"][NsField.number_of_replicas], maximum=maximum_number_of_replicas):
            # a large value exceeding limits should not work
            try:
                res_0 = tensor_search.create_vector_index(
                    index_name=self.index_name_1, config=self.config,
                    index_settings={
                        "index_defaults": {
                            "treat_urls_and_pointers_as_images": True,
                            "model": "ViT-B/32",
                        },
                        NsField.number_of_replicas: large_intended_replicas_count
                    }
                )
                raise AssertionError
            except InvalidArgError as e:
                pass

            try:
                tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
            except IndexNotFoundError:
                pass

            # a small value should work
            res_1 = tensor_search.create_vector_index(
                index_name=self.index_name_1, config=self.config,
                index_settings={
                    "index_defaults": {
                        "treat_urls_and_pointers_as_images": True,
                        "model": "ViT-B/32",
                    },
                    NsField.number_of_replicas: small_intended_replicas_count
                }
            )
            resp = requests.get(
                url=self.authorized_url + f"/{self.index_name_1}",
                headers=self.generic_header,
                verify=False
            )
            assert small_intended_replicas_count == int(
                resp.json()[self.index_name_1]['settings']['index']['number_of_replicas'])

            try:
                tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
            except IndexNotFoundError:
                pass

            # the same number should also work
            res_1 = tensor_search.create_vector_index(
                index_name=self.index_name_1, config=self.config,
                index_settings={
                    "index_defaults": {
                        "treat_urls_and_pointers_as_images": True,
                        "model": "ViT-B/32",
                    },
                    NsField.number_of_replicas: maximum_number_of_replicas
                }
            )
            resp = requests.get(
                url=self.authorized_url + f"/{self.index_name_1}",
                headers=self.generic_header,
                verify=False
            )
            assert maximum_number_of_replicas == int(
                resp.json()[self.index_name_1]['settings']['index']['number_of_replicas'])

    def test_default_max_number_of_replicas(self):
        large_intended_replicas_count = 2
        small_intended_replicas_count = 0
        # a large value exceeding limits should not work
        try:
            res_0 = tensor_search.create_vector_index(
                index_name=self.index_name_1, config=self.config,
                index_settings={
                    "index_defaults": {
                        "treat_urls_and_pointers_as_images": True,
                        "model": "ViT-B/32",
                    },
                    NsField.number_of_replicas: large_intended_replicas_count
                }
            )
            raise AssertionError
        except InvalidArgError as e:
            pass

        # a small value should work
        res_1 = tensor_search.create_vector_index(
            index_name=self.index_name_1, config=self.config,
            index_settings={
                "index_defaults": {
                    "treat_urls_and_pointers_as_images": True,
                    "model": "ViT-B/32",
                },
                NsField.number_of_replicas: small_intended_replicas_count
            }
        )
        resp = requests.get(
            url=self.authorized_url + f"/{self.index_name_1}",
            headers=self.generic_header,
            verify=False
        )
        assert small_intended_replicas_count == int(
            resp.json()[self.index_name_1]['settings']['index']['number_of_replicas'])

    def test_field_limits(self):
        index_limits = [1, 5, 10, 100, 1000]
        for lim in index_limits:
            try:
                tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
            except IndexNotFoundError as s:
                pass
            mock_read_env_vars = mock.MagicMock()
            mock_read_env_vars.return_value = lim

            @mock.patch.dict(os.environ, {**os.environ, **{EnvVars.MARQO_MAX_INDEX_FIELDS: str(lim)}})
            def run():
                tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1)
                res_1 = tensor_search.add_documents(
                    add_docs_params=AddDocsParams(
                        index_name=self.index_name_1, docs=[
                            {f"f{i}": "some content" for i in range(lim)},
                            {"_id": "1234", **{f"f{i}": "new content" for i in range(lim)}},
                        ],
                        auto_refresh=True, device="cpu"),
                    config=self.config
                )
                assert not res_1['errors']
                res_1_2 = tensor_search.add_documents(
                    add_docs_params=AddDocsParams(index_name=self.index_name_1, docs=[
                            {'f0': 'this is fine, but there is no resiliency.'},
                            {f"f{i}": "some content" for i in range(lim // 2 + 1)},
                            {'f0': 'this is fine. Still no resilieny.'}],
                        auto_refresh=True, device="cpu"),
                    config=self.config
                )
                assert not res_1_2['errors']
                try:
                    res_2 = tensor_search.add_documents(
                        add_docs_params=AddDocsParams(
                            index_name=self.index_name_1,
                            docs=[{'fx': "blah"}],
                            auto_refresh=True, device="cpu"),
                        config=self.config
                    )
                    raise AssertionError
                except errors.IndexMaxFieldsError:
                    pass
                return True
            assert run()

    def test_field_limit_non_text_types(self):
        @mock.patch.dict(os.environ, {**os.environ, **{EnvVars.MARQO_MAX_INDEX_FIELDS: "5"}})
        def run():
            docs = [
                {"f1": "fgrrvb", "f2": 1234, "f3": 1.4, "f4": "hello hello", "f5": False, "_id": "hehehehe"},
                {"f1": "erf1f", "f2": 934, "f3": 4.0, "f4": "my name", "f5": True},
                {"f1": "water is healthy", "f5": True},
                {"f2": 49, "f3": 400.4, "f4": "alien message"}
            ]
            tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1)
            res_1 = tensor_search.add_documents(
                add_docs_params=AddDocsParams(index_name=self.index_name_1, docs=docs, auto_refresh=True, device="cpu"),
                config=self.config
            )
            assert not res_1['errors']
            try:
                res_2 = tensor_search.add_documents(
                    add_docs_params=AddDocsParams(
                        index_name=self.index_name_1, docs=[
                            {'fx': "blah"}
                        ], auto_refresh=True, device="cpu"),
                    config=self.config
                )
                raise AssertionError
            except errors.IndexMaxFieldsError:
                pass
            return True

        assert run()

    def test_field_limit_none_env_var(self):
        """When the max index fields env var is undefined: we need to manually test it,
        as the testing environment may have this env var defined."""

        def run():
            docs = [
                {"f1": "fgrrvb", "f2": 1234, "f3": 1.4, "f4": "hello hello", "f5": False},
                {"f1": "erf1f", "f2": 934, "f3": 4.0, "f4": "my name", "f5": True},
                {"f1": "water is healthy", "f5": True},
                {"f2": 49, "f3": 400.4, "f4": "alien message", "_id": "rkjn"}
            ]
            tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1)
            res_1 = tensor_search.add_documents(
                add_docs_params=AddDocsParams(index_name=self.index_name_1, docs=docs, auto_refresh=True, device="cpu"),
                config=self.config
            )
            mapping_info = requests.get(
                self.authorized_url + f"/{self.index_name_1}/_mapping",
                verify=False
            )
            assert not res_1['errors']
            return True
        
        def mock_read_env_vars_and_defaults(var):
            # Read env vars should return None for MARQO_MAX_INDEX_FIELDS
            if var == EnvVars.MARQO_MAX_INDEX_FIELDS:
                return None
            else:
                return read_env_vars_and_defaults(var)
        
        with mock.patch("marqo.tensor_search.utils.read_env_vars_and_defaults", side_effect=mock_read_env_vars_and_defaults):
            assert run()

    def test_create_index_protected_name(self):
        try:
            tensor_search.create_vector_index(config=self.config, index_name='.opendistro_security')
            raise AssertionError
        except errors.InvalidIndexNameError:
            pass

    def test_create_index_protected_name_bulk(self):
        """Tests that validation prevents the user from creating an index called 'bulk' """
        # an index that contains the "bulk" substring is allowed: 
        tensor_search.create_vector_index(config=self.config, index_name='some-bulk')
        tensor_search.create_vector_index(config=self.config, index_name='bulkabc')
        # but an index name that exaclty matches "bulk" is not:
        try:
            tensor_search.create_vector_index(config=self.config, index_name='bulk')
            raise AssertionError
        except errors.InvalidIndexNameError:
            pass
        # ensure the index was not accidentally created despite the error:
        assert {'index_name': 'bulk'} not in tensor_search.get_indexes(config=self.config)['results']
        
        # but an index names with 'bulk' as a substring should appear as expected:
        assert {'index_name': 'some-bulk'} in tensor_search.get_indexes(config=self.config)['results']
        assert {'index_name': 'bulkabc'} in tensor_search.get_indexes(config=self.config)['results'] 
        
        # cleanup: 
        tensor_search.delete_index(config=self.config, index_name='some-bulk')
        tensor_search.delete_index(config=self.config, index_name='bulkabc')

    def test_index_validation_bad(self):
        bad_settings = {
            "index_defaults": {
                "treat_urls_and_pointers_as_images": False,
                "model": "hf/all_datasets_v4_MiniLM-L6",
                "normalize_embeddings": True,
                "text_preprocessing": {
                    "split_length": "2",
                    "split_overlap": "0",
                    "split_method": "sentence"
                },
                "image_preprocessing": {
                    "patch_method": None
                }
            },
            "number_of_shards": 5,
            "number_of_replicas": 1
        }
        try:
            tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, index_settings=bad_settings)
            raise AssertionError
        except errors.InvalidArgError as e:
            pass

    def test_index_validation_good(self):
        good_settings = {
            "index_defaults": {
                "treat_urls_and_pointers_as_images": False,
                "model": "hf/all_datasets_v4_MiniLM-L6",
                "normalize_embeddings": True,
                "text_preprocessing": {
                    "split_length": 2,
                    "split_overlap": 0,
                    "split_method": "sentence"
                },
                "image_preprocessing": {
                    "patch_method": None
                }
            },
            "number_of_shards": 5,
            "number_of_replicas": 1
        }
        tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, index_settings=good_settings)

    def test_custom_model_with_no_model_properties_fails(self):
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError:
            pass
        bad_settings = {
            "index_defaults": {
                "model": "my-custom-model",
            },
        }
        try:
            tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, index_settings=bad_settings)
            raise AssertionError
        except errors.InvalidArgError as e:
            pass
    
    def test_custom_model_with_no_dimensions_fails(self):
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError:
            pass
        bad_settings = {
            "index_defaults": {
                "model": "my-custom-model",
                "model_properties": {
                    "url": "https://www.random.com",
                    "type": "open_clip"
                    # no dimensions here
                }
            },
        }
        try:
            tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, index_settings=bad_settings)
            raise AssertionError
        except errors.InvalidArgError as e:
            pass
    
    def test_custom_model_with_dimensions_wrong_type_fails(self):
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError:
            pass
        bad_settings = {
            "index_defaults": {
                "model": "my-custom-model",
                "model_properties": {
                    "url": "https://www.random.com",
                    "type": "open_clip",
                    "dimensions": "BAD DATATYPE!! should be int."
                }
            },
        }
        try:
            tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, index_settings=bad_settings)
            raise AssertionError
        # TODO: This 500 is fine as user sees their mistake, but we should change it to a 400 later.
        except errors.MarqoWebError as e:
            pass
    
    def test_custom_model_with_bad_properties_fails_add_docs(self):
        try:
            tensor_search.delete_index(config=self.config, index_name=self.index_name_1)
        except IndexNotFoundError:
            pass
        bad_settings = {
            "index_defaults": {
                "model": "my-custom-model",
                "model_properties": {
                    "url": "https://www.random.com",
                    "type": "open_clip",
                    "dimensions": 123  # random number, should be 512
                }
            },
        }
        
        # creating index should work fine
        # but when you add docs, it fails (when trying to load the model)
        tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, index_settings=bad_settings)
        docs = [
            {"f1": "water is healthy", "f5": True},
            {"f2": 49, "f3": 400.4, "f4": "alien message", "_id": "rkjn"}
        ]
        try:
            tensor_search.add_documents(
                add_docs_params=AddDocsParams(index_name=self.index_name_1, docs=docs, auto_refresh=True, device="cpu"),
                config=self.config
            )
            raise AssertionError
        except errors.MarqoWebError as e:
            pass
    
    def _fill_in_test_model_data(self, test_model_data):
        """
        Helper function to fill in test model data with index defaults
        Returns index settings object with no knn field
        """
        return {
            'settings': {
                'index': {
                    'knn': True, 
                    'knn.algo_param.ef_search': 100, 
                    'refresh_interval': '1s', 
                    'store.hybrid.mmap.extensions': ['nvd', 'dvd', 'tim', 'tip', 'dim', 'kdd', 'kdi', 'cfs', 'doc', 'vec', 'vex']
                }, 
                'number_of_shards': 5, 
                'number_of_replicas': 1
            }, 
            'mappings': {
                '_meta': {
                    'media_type': 'text', 
                    'index_settings': {
                        'index_defaults': {
                            'treat_urls_and_pointers_as_images': False, 
                            **test_model_data,  # has model and possibly model_properties
                            'normalize_embeddings': True, 
                            'text_preprocessing': {
                                'split_length': 2, 
                                'split_overlap': 0, 
                                'split_method': 'sentence'
                            }, 
                            'image_preprocessing': {'patch_method': None}, 
                            'ann_parameters': {
                                'name': 'hnsw', 
                                'space_type': 'cosinesimil', 
                                'engine': 'lucene', 
                                'parameters': {'ef_construction': 128, 'm': 16}
                            }
                        }, 
                        'number_of_shards': 5, 
                        'number_of_replicas': 1
                    }, 
                    'model': 'hf/all_datasets_v4_MiniLM-L6',
                    'search_model': 'hf/all_datasets_v4_MiniLM-L6'
                }, 
                'dynamic_templates': [{
                    'strings': {
                        'match_mapping_type': 'string', 
                        'mapping': {'type': 'text'}
                    }
                }], 
                'properties': {
                    '__chunks': {
                        'type': 'nested', 
                        'properties': {
                            '__field_name': {'type': 'keyword'}, 
                            '__field_content': {'type': 'text'}
                        }
                    }
                }
            }
        }

    def test_add_knn_field(self):
        """
        Tests helper function to add OpenSearch KNN Field to index mappings
        """
        test_cases = (
            # format: (model_data, expected_knn_properties)
            # model in registry
            (
                {
                    "model": "hf/all_datasets_v4_MiniLM-L6",
                    "search_model": "hf/all_datasets_v4_MiniLM-L6"
                }, 
                {
                    'type': 'knn_vector', 
                    'dimension': 384, 
                    'method': {
                        'name': 'hnsw', 
                        'space_type': 'cosinesimil', 
                        'engine': 'lucene', 
                        'parameters': {'ef_construction': 128, 'm': 16}
                    }
                }
            ),
            # custom model
            (
                {
                    "model": "my-custom-model", 
                    "model_properties": {"url": "https://www.random.com", "type": "open_clip", "dimensions": 512},
                    "search_model": "my-custom-model",
                    "search_model_properties": {"url": "https://www.random.com", "type": "open_clip", "dimensions": 512}
                },
                {
                    'type': 'knn_vector', 
                    'dimension': 512,   # dimension should match custom model properties
                    'method': {
                        'name': 'hnsw', 
                        'space_type': 'cosinesimil', 
                        'engine': 'lucene', 
                        'parameters': {'ef_construction': 128, 'm': 16}
                    }
                }
            )
        )

        for model_data, expected_knn_properties in test_cases:
            # create raw index settings object
            index_settings_no_knn = self._fill_in_test_model_data(model_data)
            # add knn field
            index_settings_with_knn = tensor_search._add_knn_field(index_settings_no_knn)
            # check that knn field was added
            assert index_settings_with_knn["mappings"]["properties"][TensorField.chunks]["properties"][TensorField.marqo_knn_field] \
                == expected_knn_properties
    
    def test_add_knn_field_failures(self):
        test_cases = (
            # custom model with no model properties
            ({"model": "my-custom-model", "search_model": "hf/all_datasets_v4_MiniLM-L6"}, 
             errors.InvalidArgError),
            # custom search_model with no search_model_properties
            ({"model": "hf/all_datasets_v4_MiniLM-L6", "search_model": "my_custom_search_model"}, 
             errors.InvalidArgError),
            # custom model with model properties but no dimensions
            ({
                "model": "my-custom-model", 
                "model_properties": {"url": "https://www.random.com", "type": "open_clip"},
                "search_model": "hf/all_datasets_v4_MiniLM-L6"
            },
             errors.InvalidArgError),
        )

        for model_data, error_type in test_cases:
            try:
                index_settings_no_knn = self._fill_in_test_model_data(model_data)
                tensor_search._add_knn_field(index_settings_no_knn)
                raise AssertionError
            except error_type:
                pass
    
    def test_create_index_no_model_invalid(self):
        test_cases = [
            # No model properties
            (
                {
                    "model": "no_model",
                },
                "must provide `model_properties`"
            ),
            # No dimensions
            (
                {
                    "model": "no_model",
                    "model_properties": {}
                },
                "must have `dimensions` set"
            ),
            # Extra key (prevents users trying to make Generic CLIP index from using `no_model`)
            (
                {
                    "model": "no_model",
                    "model_properties": {"dimensions": 123, "url": "http://www.random.com", "type": "CLIP"}
                },
                "Invalid model_properties key found:"
            ),
            # Wrong dimensions type
            (
                {
                    "model": "no_model",
                    "model_properties": {"dimensions": 123.45}
                },
                "must be a positive integer"
            ),
            # Wrong dimensions type
            (
                {
                    "model": "no_model",
                    "model_properties": {"dimensions": "hello"}
                },
                "must be a positive integer"
            ),
        ]

        for case, error_message in test_cases:
            try:
                tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, index_settings={NsField.index_defaults: case})
                raise AssertionError
            except errors.InvalidArgError as e:
                assert error_message in e.message
    
    def test_create_index_no_model_valid(self):
        """
        Index must be created with the correct dimensions.
        """
        tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, 
                                          index_settings={
                                              NsField.index_defaults: {"model": "no_model", "model_properties": {"dimensions": 123}}
                                        })

        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model_properties"]["dimensions"] == 123
    
    def test_create_index_with_search_model_valid(self):
        """
        Ensures that indexes can be created with search_model and search_model_properties
        Should have correct interactions with model and model_properties.
        """

        # model only (search model should be set to model)
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, 
            index_settings={
                NsField.index_defaults: {
                    "model": "ViT-B/32",          # dimension is 512
                }
            }
        )
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "ViT-B/32"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "ViT-B/32"
        assert index_info.model_name == "ViT-B/32"
        assert index_info.search_model_name == "ViT-B/32"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert fetched_model_properties["type"] == "clip"
        assert fetched_search_model_properties["dimensions"] == 512
        assert fetched_search_model_properties["type"] == "clip"
        tensor_search.delete_index(config=self.config, index_name=self.index_name_1)

        # model and model_properties (search model should be set to model, search model properties set to model properties)
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, 
            index_settings={
                NsField.index_defaults: {
                    "model": "my_custom_model",          # dimension is 512
                    "model_properties": {
                        "name": "ViT-B/32",
                        "dimensions": 512,
                        "url": "https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt",
                        "type": "clip",
                    },
                }
            }
        )
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "my_custom_model"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "my_custom_model"
        assert index_info.model_name == "my_custom_model"
        assert index_info.search_model_name == "my_custom_model"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert fetched_model_properties["type"] == "clip"
        assert fetched_search_model_properties["dimensions"] == 512
        assert fetched_search_model_properties["type"] == "clip"
        tensor_search.delete_index(config=self.config, index_name=self.index_name_1)

        # model and search_model (both in registry)
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, 
            index_settings={
                NsField.index_defaults: {
                    "model": "ViT-B/32",          # dimension is 512
                    "search_model": "onnx32/open_clip/ViT-B-32/laion2b_e16"   # dimension is 512
                }
            }
        )
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "ViT-B/32"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "onnx32/open_clip/ViT-B-32/laion2b_e16"
        assert index_info.model_name == "ViT-B/32"
        assert index_info.search_model_name == "onnx32/open_clip/ViT-B-32/laion2b_e16"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert fetched_model_properties["type"] == "clip"
        assert fetched_search_model_properties["dimensions"] == 512
        assert fetched_search_model_properties["type"] == "clip_onnx"
        tensor_search.delete_index(config=self.config, index_name=self.index_name_1)

        # model, model_properties, search_model, search_model_properties (both custom)
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, 
            index_settings={
                NsField.index_defaults: {
                    "model": "my_custom_model",          # dimension is 512
                    "model_properties": {
                        "name": "ViT-B/32",
                        "dimensions": 512,
                        "url": "https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt",
                        "type": "clip",
                    },
                    "search_model": "my_custom_search_model",
                    "search_model_properties": {
                        "name": "ViT-B-32-quickgelu",
                        "dimensions": 512,
                        "url": "https://github.com/mlfoundations/open_clip/releases/download/v0.2-weights/vit_b_32-quickgelu-laion400m_avg-8a00ab3c.pt",
                        "type": "open_clip",
                    }
                }
            }
        )
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "my_custom_model"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "my_custom_search_model"
        assert index_info.model_name == "my_custom_model"
        assert index_info.search_model_name == "my_custom_search_model"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert fetched_model_properties["type"] == "clip"
        assert fetched_search_model_properties["dimensions"] == 512
        assert fetched_search_model_properties["type"] == "open_clip"
        tensor_search.delete_index(config=self.config, index_name=self.index_name_1)

        # model, model_properties, search_model (model in registry, search_model is custom)
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, 
            index_settings={
                NsField.index_defaults: {
                    "model": "ViT-B/32",          # dimension is 512
                    "search_model": "my_custom_search_model",
                    "search_model_properties": {
                        "name": "ViT-B-32-quickgelu",
                        "dimensions": 512,
                        "url": "https://github.com/mlfoundations/open_clip/releases/download/v0.2-weights/vit_b_32-quickgelu-laion400m_avg-8a00ab3c.pt",
                        "type": "open_clip",
                    }
                }
            }
        )
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "ViT-B/32"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "my_custom_search_model"
        assert index_info.model_name == "ViT-B/32"
        assert index_info.search_model_name == "my_custom_search_model"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert fetched_model_properties["type"] == "clip"
        assert fetched_search_model_properties["dimensions"] == 512
        assert fetched_search_model_properties["type"] == "open_clip"
        tensor_search.delete_index(config=self.config, index_name=self.index_name_1)

        # model, search_model is no_model
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, 
            index_settings={
                NsField.index_defaults: {
                    "model": "ViT-B/32",          # dimension is 512
                    "search_model": "no_model",
                    "search_model_properties": {
                        "dimensions": 512
                    }
                }
            }
        )
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "ViT-B/32"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "no_model"
        assert index_info.model_name == "ViT-B/32"
        assert index_info.search_model_name == "no_model"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert fetched_model_properties["type"] == "clip"
        assert fetched_search_model_properties["dimensions"] == 512
        assert "type" not in fetched_search_model_properties
        tensor_search.delete_index(config=self.config, index_name=self.index_name_1)

        # model is no_model, search_model
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, 
            index_settings={
                NsField.index_defaults: {
                    "model": "no_model",
                    "model_properties": {
                        "dimensions": 512
                    },                 
                    "search_model": "ViT-B/32"
                }
            }
        )
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "no_model"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "ViT-B/32"
        assert index_info.model_name == "no_model"
        assert index_info.search_model_name == "ViT-B/32"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert "type" not in fetched_model_properties
        assert fetched_search_model_properties["dimensions"] == 512
        assert fetched_search_model_properties["type"] == "clip"
        tensor_search.delete_index(config=self.config, index_name=self.index_name_1)

    def test_create_index_with_search_model_and_update(self):
        """
        Ensures that index settings stay correct with search model even after adding new fields to index.
        """
        tensor_search.create_vector_index(
            config=self.config, index_name=self.index_name_1, 
            index_settings={
                NsField.index_defaults: {
                    "model": "my_custom_model",          # dimension is 512
                    "model_properties": {
                        "name": "ViT-B/32",
                        "dimensions": 512,
                        "url": "https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt",
                        "type": "clip",
                    },
                    "search_model": "my_custom_search_model",
                    "search_model_properties": {
                        "name": "ViT-B-32-quickgelu",
                        "dimensions": 512,
                        "url": "https://github.com/mlfoundations/open_clip/releases/download/v0.2-weights/vit_b_32-quickgelu-laion400m_avg-8a00ab3c.pt",
                        "type": "open_clip",
                    }
                }
            }
        )
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "my_custom_model"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "my_custom_search_model"
        assert index_info.model_name == "my_custom_model"
        assert index_info.search_model_name == "my_custom_search_model"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert fetched_model_properties["type"] == "clip"
        assert fetched_search_model_properties["dimensions"] == 512
        assert fetched_search_model_properties["type"] == "open_clip"
        
        # Add normal text and multimodal fields to index
        tensor_search.add_documents(
            config=self.config, add_docs_params=AddDocsParams(
                index_name=self.index_name_1,
                docs=[{
                    "_id": "0",
                    "text_field": "blah",
                    "my_custom_vector": {
                        "content": "custom content is here!!",
                        "vector": [1.0 for _ in range(512)]
                    },
                    "my_multimodal": {
                        "text": "multimodal text",
                        "image": 'https://marqo-assets.s3.amazonaws.com/tests/images/ai_hippo_realistic.png'
                    }
                }],
                auto_refresh=True, device="cpu", 
                mappings={
                    "my_custom_vector": {
                        "type": "custom_vector"
                    },
                    "my_multimodal": {
                        "type": "multimodal_combination",
                        "weights": {
                            "text": 0.4,
                            "image": 0.6
                        }
                    }
                }
            )
        )

        # index settings should remain the same
        index_info = backend.get_index_info(config=self.config, index_name=self.index_name_1)
        assert index_info.index_settings[NsField.index_defaults]["model"] == "my_custom_model"
        assert index_info.index_settings[NsField.index_defaults]["search_model"] == "my_custom_search_model"
        assert index_info.model_name == "my_custom_model"
        assert index_info.search_model_name == "my_custom_search_model"

        fetched_model_properties = index_info.get_model_properties()
        fetched_search_model_properties = index_info.get_search_model_properties()
        assert fetched_model_properties["dimensions"] == 512
        assert fetched_model_properties["type"] == "clip"
        assert fetched_search_model_properties["dimensions"] == 512
        assert fetched_search_model_properties["type"] == "open_clip"

    def test_create_index_with_search_model_invalid(self):
        """
        Ensures that creating an index with search_model with improper settings fails with the correct error message.
        """
        test_cases = [
            # Different dimensions for model and search_model (in registry)
            {
                "defaults": {
                    "model": "ViT-B/32",    # dimensions: 512
                    "search_model": "sentence-transformers/all-MiniLM-L6-v1"    # dimensions: 384
                },
                "error": InvalidArgError,
                "error_message": "must be equal"
            },

            # Different dimensions for model and search_model (custom)
            {
                "defaults": {
                    "model": "my_custom_model",
                    "model_properties": {
                        "name": "ViT-B/32",
                        "dimensions": 512,
                        "url": "https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt",
                        "type": "clip",
                    },
                    "search_model": "no_model",
                    "search_model_properties": {
                        "dimensions": 123
                    }
                },
                "error": InvalidArgError,
                "error_message": "must be equal"
            },

            # search_model has no dimensions
            {
                "defaults": {
                    "model": "ViT-B/32",    # dimensions: 512
                    "search_model": "my_custom_search_model",
                    "search_model_properties": {
                        "name": "ViT-B/32",     # no dimensions given
                        "url": "https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt",
                        "type": "clip"
                    }
                },
                "error": InvalidArgError,
                "error_message": "must contain a 'dimensions' key"
            },

            # search_model_properties but no search_model
            {
                "defaults": {
                    "model": "ViT-B/32",    # dimensions: 512
                    "search_model_properties": {
                        "dimensions": 123
                    }
                },
                "error": InvalidArgError,
                "error_message": "No `search_model` found"
            },

            # search_model but no model
            {
                "defaults": {
                    "search_model": "my_custom_search_model",
                    "search_model_properties": {
                        "name": "ViT-B/32",     # no dimensions given
                        "url": "https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt",
                        "type": "clip"
                    }
                },
                "error": InvalidArgError,
                "error_message": "found no `model`"
            },
        ]

        for case in test_cases:
            try:
                tensor_search.create_vector_index(config=self.config, index_name=self.index_name_1, index_settings={NsField.index_defaults: case["defaults"]})
                raise AssertionError
            except case["error"] as e:
                assert case["error_message"] in e.message