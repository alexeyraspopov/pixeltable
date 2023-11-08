import datetime
import pytest
import pickle
import numpy as np
from pathlib import Path

from pixeltable import catalog
from pixeltable import exceptions as exc
from pixeltable import DataFrame
from pixeltable.functions import dict_map, cast, sum, count
import pixeltable as pt
import PIL.Image

class TestDataFrame:
    def test_select_where(self, test_tbl: catalog.Table) -> None:
        t = test_tbl
        res1 = t[t.c1, t.c2, t.c3].show(0)
        res2 = t.select(t.c1, t.c2, t.c3).show(0)
        assert res1 == res2

        res1 = t[t.c2 < 10][t.c1, t.c2, t.c3].show(0)
        res2 = t.where(t.c2 < 10).select(t.c1, t.c2, t.c3).show(0)
        assert res1 == res2

        res3 = t.where(t.c2 < 10).select(c1=t.c1, c2=t.c2, c3=t.c3).show(0)
        assert res1 == res3

        res4 = t.where(t.c2 < 10).select(t.c1, c2=t.c2, c3=t.c3).show(0)
        assert res1 == res4

        _ = t.where(t.c2 < 10).select(t.c2, t.c2).show(0) # repeated name no error
        
        # duplicate select list
        with pytest.raises(exc.Error) as exc_info:
            _ = t.select(t.c1).select(t.c2).show(0)
        assert 'already specified' in str(exc_info.value)

        # invalid expr in select list: Callable is not a valid literal
        with pytest.raises(TypeError) as exc_info:
            _ = t.select(datetime.datetime.now).show(0)
        assert 'Not a valid literal' in str(exc_info.value)

        # catch invalid name in select list from user input
        # only check stuff that's not caught by python kwargs checker
        with pytest.raises(exc.Error) as exc_info:
            _ = t.select(t.c1, **{'c2-1': t.c2}).show(0)
        assert 'Invalid name' in str(exc_info.value)

        with pytest.raises(exc.Error) as exc_info:
            _ = t.select(t.c1, **{'': t.c2}).show(0)
        assert 'Invalid name' in str(exc_info.value)

        with pytest.raises(exc.Error) as exc_info:
            _ = t.select(t.c1, **{'foo.bar': t.c2}).show(0)
        assert 'Invalid name' in str(exc_info.value)

        with pytest.raises(exc.Error) as exc_info:
            _ = t.select(t.c1, _c3=t.c2).show(0)
        assert 'Invalid name' in str(exc_info.value)

        # catch repeated name from user input
        with pytest.raises(exc.Error) as exc_info:
            _ = t.select(t.c2, c2=t.c1).show(0)
        assert 'Repeated column name' in str(exc_info.value)

        with pytest.raises(exc.Error) as exc_info:
            _ = t.select(t.c2+1, col_0=t.c2).show(0)
        assert 'Repeated column name' in str(exc_info.value)

    def test_order_by(self, test_tbl: catalog.Table) -> None:
        t = test_tbl
        res = t.select(t.c4, t.c2).order_by(t.c4).order_by(t.c2, asc=False).show(0)

        # invalid expr in order_by()
        with pytest.raises(exc.Error) as exc_info:
            _ = t.order_by(datetime.datetime.now()).show(0)
        assert 'Invalid expression' in str(exc_info.value)

    def test_head(self, test_tbl: catalog.Table) -> None:
        t = test_tbl
        assert t.head() == t.show()
        assert t.head(10) == t.show(10)
        assert t.head(10) == t.df().limit(10).collect()

    def test_describe(self, test_tbl: catalog.Table) -> None:
        t = test_tbl
        df = t.select(t.c1).where(t.c2 < 10).limit(10)
        df.describe()

        # TODO: how to you check the output of these?
        _ = df.__repr__()
        _ = df._repr_html_()

    def test_count(self, test_tbl: catalog.Table, indexed_img_tbl: catalog.Table) -> None:
        t = test_tbl
        cnt = t.count()
        assert cnt == 100

        cnt = t.where(t.c2 < 10).count()
        assert cnt == 10

        # count() doesn't work with similarity search
        t = indexed_img_tbl
        probe = t.select(t.img).show(1)
        img = probe[0, 0]
        with pytest.raises(exc.Error):
            _ = t.where(t.img.nearest(img)).count()
        with pytest.raises(exc.Error):
            _ = t.where(t.img.nearest('car')).count()

        # for now, count() doesn't work with non-SQL Where clauses
        with pytest.raises(exc.Error):
            _ = t.where(t.img.width > 100).count()

    def test_select_literal(self, test_tbl: catalog.Table) -> None:
        t = test_tbl
        res = t.select(1.0).where(t.c2 < 10).show(0)
        assert res.rows == [[1.0]] * 10

    def test_to_pytorch_dataset(self, all_datatype_tbl: catalog.Table):
        """ tests all types are handled correctly in this conversion
        """
        import torch

        t = all_datatype_tbl
        df = t.where(t.row_id < 1)
        assert df.count() > 0
        ds = df.to_pytorch_dataset()
        type_dict = dict(zip(df.get_column_names(),df.get_column_types()))
        for tup in ds:
            for col in df.get_column_names():
                assert col in tup
        
            arrval = tup['c_array']
            assert isinstance(arrval, np.ndarray)
            col_type = type_dict['c_array']
            assert arrval.dtype == col_type.numpy_dtype()
            assert arrval.shape == col_type.shape
            assert arrval.dtype == np.float32

            assert isinstance(tup['c_bool'], bool)
            assert isinstance(tup['c_int'], int)
            assert isinstance(tup['c_float'], float)
            assert isinstance(tup['c_timestamp'], float)
            assert torch.is_tensor(tup['c_image'])
            assert isinstance(tup['c_video'], str)
            assert isinstance(tup['c_json'], dict)

    def test_to_pytorch_image_format(self, all_datatype_tbl: catalog.Table) -> None:
        """ tests the image_format parameter is honored
        """
        import torch
        import torchvision.transforms as T

        W, H = 220, 224 # make different from each other
        t = all_datatype_tbl
        df = t.select(
            t.row_id,
            t.c_image,
            c_image_xformed=t.c_image.resize([W, H]).convert('RGB')
        ).where(t.row_id < 1)

        pandas_df = df.show().to_pandas()
        im_plain = pandas_df['c_image'].values[0]
        im_xformed = pandas_df['c_image_xformed'].values[0]
        assert pandas_df.shape[0] == 1

        ds = df.to_pytorch_dataset(image_format='np')
        ds_ptformat = df.to_pytorch_dataset(image_format='pt')

        elt_count = 0
        for elt, elt_pt in zip(ds, ds_ptformat):
            arr_plain = elt['c_image']
            assert isinstance(arr_plain, np.ndarray)
            # NB: compare numpy array bc PIL.Image object itself is not using same file.
            assert (arr_plain == np.array(im_plain)).all(), 'numpy image should be the same as the original'
            arr_xformed = elt['c_image_xformed']
            assert isinstance(arr_xformed, np.ndarray)
            assert arr_xformed.shape == (H, W, 3)
            assert arr_xformed.dtype == np.uint8
            # same as above, compare numpy array bc PIL.Image object itself is not using same file.
            assert (arr_xformed == np.array(im_xformed)).all(), 'numpy image array for xformed image should be the same as the original'

            # now compare pytorch version
            arr_pt = elt_pt['c_image']
            assert torch.is_tensor(arr_pt)
            arr_pt = elt_pt['c_image_xformed']
            assert torch.is_tensor(arr_pt)
            assert arr_pt.shape == (3, H, W)
            assert arr_pt.dtype == torch.float32
            assert (0.0 <= arr_pt).all()
            assert (arr_pt <= 1.0).all()
            assert torch.isclose(T.ToTensor()(arr_xformed), arr_pt).all(), 'pytorch image should be consistent with numpy image'
            elt_count += 1
        assert elt_count == 1

    def test_to_pytorch_dataloader(self, all_datatype_tbl: catalog.Table):
        """ Tests the dataset works well with pytorch dataloader:
            1. compatibility with multiprocessing
            2. compatibility of all types with default collate_fn
        """
        import torch.utils.data
        @pt.function(param_types=[pt.JsonType()], return_type=pt.JsonType())
        def restrict_json_for_default_collate(obj):
            keys = ['id', 'label', 'iscrowd', 'bounding_box']
            return {k: obj[k] for k in keys}
        
        t = all_datatype_tbl
        df = t.select(
            t.row_id,
            t.c_int,
            t.c_float,
            t.c_bool,
            t.c_timestamp,
            t.c_array,
            t.c_video,
            # default collate_fn doesnt support null values, nor lists of different lengths
            # but does allow some dictionaries if they are uniform
            c_json = restrict_json_for_default_collate(t.c_json.detections[0]),
            # images must be uniform shape for pytorch collate_fn to not fail
            c_image=t.c_image.resize([220, 224]).convert('RGB')
        )
        df_size = df.count()
        ds = df.to_pytorch_dataset(image_format='pt')
        # test serialization:
        #  - pickle.dumps() and pickle.loads() must work so that
        #   we can use num_workers > 0
        x = pickle.dumps(ds)
        _ = pickle.loads(x)

        # test we get all rows
        def check_recover_all_rows(ds, size : int, **kwargs):
            dl = torch.utils.data.DataLoader(ds, **kwargs)
            loaded_ids = set()
            for batch in dl:
                for row_id in batch['row_id']:
                    val = int(row_id) # np.int -> int or will fail set equality test below.
                    assert val not in loaded_ids, val
                    loaded_ids.add(val)

            assert loaded_ids == set(range(size))

        # check different number of workers
        check_recover_all_rows(ds, size=df_size, batch_size=3, num_workers=0) # within this process
        check_recover_all_rows(ds, size=df_size, batch_size=3, num_workers=2) # two separate processes

        # check edge case where some workers get no rows
        short_size = 1
        df_short = df.where(t.row_id < short_size)
        ds_short = df_short.to_pytorch_dataset(image_format='pt')
        check_recover_all_rows(ds_short, size=short_size, batch_size=13, num_workers=short_size+1)

    def test_pytorch_dataset_caching(self, all_datatype_tbl: catalog.Table):
        """ Tests that dataset caching works
            1. using the same dataset twice in a row uses the cache
            2. adding a row to the table invalidates the cached version
            3. changing the select list invalidates the cached version
        """
        t = all_datatype_tbl

        t.drop_column('c_video') # null value video column triggers internal assertions in DataRow
        # see https://github.com/mkornacker/pixeltable/issues/38

        t.drop_column('c_array') # no support yet for null array values in the pytorch dataset

        def _get_mtimes(dir: Path):
            return {p.name: p.stat().st_mtime for p in dir.iterdir()}

        #  check result cached
        ds1 = t.to_pytorch_dataset(image_format='pt')
        ds1_mtimes = _get_mtimes(ds1.path)
        
        ds2 = t.to_pytorch_dataset(image_format='pt')
        ds2_mtimes = _get_mtimes(ds2.path)
        assert ds2.path == ds1.path, 'result should be cached'
        assert ds2_mtimes == ds1_mtimes, 'no extra file system work should have occurred'

        # check invalidation on insert
        t_size = t.count()
        t.insert([[t_size, ]], columns=['row_id'])
        ds3 = t.to_pytorch_dataset(image_format='pt')
        assert ds3.path != ds1.path, 'different path should be used'

        # check select list invalidation
        ds4 = t.select(t.row_id).to_pytorch_dataset(image_format='pt')
        assert ds4.path != ds3.path, 'different select list, hence different path should be used'



