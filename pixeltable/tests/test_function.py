import pytest

from pixeltable.function import Function, FunctionRegistry
from pixeltable.type_system import IntType, FloatType
from pixeltable import catalog
import pixeltable as pt
from pixeltable import exceptions as exc


def dummy_fn(i: int) -> int:
    return i

class TestFunction:
    eval_fn = lambda x: x + 1
    func = Function(IntType(), [IntType()], eval_fn=eval_fn)

    class Aggregator:
        def __init__(self):
            self.sum = 0
        @classmethod
        def make_aggregator(cls) -> 'Aggregator':
            return cls()
        def update(self, val) -> None:
            if val is not None:
                self.sum += val
        def value(self):
            return self.sum
    agg = Function(
        IntType(), [IntType()],
        init_fn=Aggregator.make_aggregator, update_fn=Aggregator.update, value_fn=Aggregator.value)

    def test_serialize_anonymous(self, init_db: None) -> None:
        d = self.func.as_dict()
        FunctionRegistry.get().clear_cache()
        deserialized = Function.from_dict(d)
        assert deserialized.eval_fn(1) == 2

    def test_create(self, test_db: catalog.Db) -> None:
        db = test_db
        db.create_function('test_fn', self.func)
        FunctionRegistry.get().clear_cache()
        cl = pt.Client()
        db2 = cl.get_db('test')
        fn2 = db2.get_function('test_fn')
        assert fn2.eval_fn(1) == 2

        with pytest.raises(exc.DuplicateNameError):
            db.create_function('test_fn', self.func)
        with pytest.raises(exc.UnknownEntityError):
            db.create_function('dir1.test_fn', self.func)
        with pytest.raises(exc.Error):
            library_fn = Function(IntType(), [IntType()], module_name=__name__, eval_symbol='dummy_fn')
            db.create_function('library_fn', library_fn)

    def test_update(self, test_db: catalog.Db, test_tbl: catalog.Table) -> None:
        db = test_db
        t = test_tbl
        db.create_function('test_fn', self.func)
        res1 = t[self.func(t.c2)].show(0).to_pandas()

        # load function from db and make sure it computes the same thing as before
        FunctionRegistry.get().clear_cache()
        cl = pt.Client()
        db = cl.get_db('test')
        fn = db.get_function('test_fn')
        res2 = t[fn(t.c2)].show(0).to_pandas()
        assert res1.col_0.equals(res2.col_0)
        fn.eval_fn = lambda x: x + 2
        db.update_function('test_fn', fn)

        FunctionRegistry.get().clear_cache()
        cl = pt.Client()
        db = cl.get_db('test')
        fn = db.get_function('test_fn')
        res3 = t[fn(t.c2)].show(0).to_pandas()
        assert (res2.col_0 + 1).equals(res3.col_0)

        # signature changes
        with pytest.raises(exc.Error):
            db.update_function('test_fn', Function(FloatType(), [IntType()], eval_fn=fn.eval_fn))
        with pytest.raises(exc.Error):
            db.update_function('test_fn', Function(IntType(), [FloatType()], eval_fn=fn.eval_fn))
        with pytest.raises(exc.Error):
            db.update_function('test_fn', self.agg)

    def test_rename(self, test_db: catalog.Db) -> None:
        db = test_db
        db.create_function('test_fn', self.func)

        FunctionRegistry.get().clear_cache()
        cl = pt.Client()
        db2 = cl.get_db('test')
        with pytest.raises(exc.UnknownEntityError):
            db2.rename_function('test_fn2', 'test_fn')
        db2.rename_function('test_fn', 'test_fn2')
        func = db2.get_function('test_fn2')
        assert func.eval_fn(1) == 2

        with pytest.raises(exc.UnknownEntityError):
            _ = db2.get_function('test_fn')

        # move function between directories
        db2.create_dir('functions')
        db2.create_dir('functions2')
        db2.create_function('functions.func1', self.func)
        with pytest.raises(exc.UnknownEntityError):
            db2.rename_function('functions2.func1', 'functions.func1')
        db2.rename_function('functions.func1', 'functions2.func1')

        FunctionRegistry.get().clear_cache()
        cl = pt.Client()
        db3 = cl.get_db('test')
        func = db3.get_function('functions2.func1')
        assert func.eval_fn(1) == 2
        with pytest.raises(exc.UnknownEntityError):
            _ = db3.get_function('functions.func1')

    def test_drop(self, test_db: catalog.Db) -> None:
        db = test_db
        db.create_function('test_fn', self.func)
        FunctionRegistry.get().clear_cache()
        cl = pt.Client()
        db2 = cl.get_db('test')
        db2.drop_function('test_fn')

        with pytest.raises(exc.UnknownEntityError):
            _ = db2.get_function('test_fn')
