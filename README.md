# Pixeltable: A Table Interface for Image and Video Data

## Installation

1. Install Postgres

    On MacOS, [postgresapp.com](postgresapp.com) is a convenient way to do that.

2. `pip install pixeltable`

3. Install additional dependencies
   - Install PyTorch (required for CLIP): see [here](https://pytorch.org/get-started/locally/).
   - Install CLIP from [here](https://github.com/openai/CLIP).
   - If you want to work with videos, you also need to install `ffmpeg`.

## Setup

Pixeltable requires a home directory and a Postgres database, and both are created automatically the
first time you create a Pixeltable client (see below). The location of the home directory is
`~/.pixeltable` (or the value of the `PIXELTABLE_HOME` environment variable). The following
environment variables determine how Pixeltable connects to the Postgres instance.

|Environment Variable|Default|
|----|----|
| `PIXELTABLE_HOME`| `~/.pixeltable` |
| `PIXELTABLE_DB`| `pixeltable` |
| `PIXELTABLE_DB_USER` | |
| `PIXELTABLE_DB_PASSWORD` | |
| `PIXELTABLE_DB_HOST` | `localhost` |
| `PIXELTABLE_DB_PORT` | `5432` |

## Overview

Import convention:
```
import pixeltable as pt
import pixeltable.functions as ptf
```

### Creating a client
```
cl = pt.Client()
```

### Client operations summary
|Action|Code|
|----|----|
| Create a database| `db = cl.create_db('db1')`|
| Use an existing database| `db = cl.get_db('db1')`|
| Delete an existing database| `cl.drop_db('db1', force=True)`|
| List all existing databases| `cl.list_dbs()`|
| List all available functions| `cl.list_functions()`|

### Database operations summary
|Action|Code|
|----|----|
| Create a table| `t = db.create_table('table_name', [pt.Column(...), ...])` |
| Use an existing table| `t = db.get_table('video_data')` |
| Rename a table| `db.rename_table('video_data', 'vd')` |
| List tables| `db.list_tables()` |
| Delete a table| `db.drop_table('video_data')` |
| Create a stored function| `db.create_function('func_name', pt.Function(...))` |
| Load a stored function| `f = db.get_function('func_name')` |
| Rename a stored function| `db.rename_function('func_name', 'better_name')` |
| Update a stored function| `db.update_function('func_name', pt.Function(...))` |
| Delete a stored function| `db.drop_function('func_name')` |

### Frame extraction for video data

Creating a table with video data and automatic frame extraction:
```
c1 = pt.Column('video', pt.VideoType())
c2 = pt.Column('frame_idx', pt.IntType())
c3 = pt.Column('frame', pt.ImageType())
t = db.create_table(
    'video_table', [c1, c2, c3],
    extract_frames_from='video',
    extracted_frame_col='frame',
    extracted_frame_idx_col='frame_idx',
    extracted_fps=1)
```

`extracted_fps=0` extracts frames at the original frame rate.

For additional filtering, add keyword argument `ffmpeg_filter={...}`, for example
```
ffmpeg_filter={'select': 'gt(scene,0.4)'}
```

### Table operations summary
|Action|Code|
|----|----|
| Print table schema | `t.describe()`|
| Query a table | `t[<column selections>][<filter expression>].show()` |
| Insert rows into a table| `t.insert_rows([<list of column values for row 1>, <row 2>, ...], columns=<list of column names>)`|
| Add a column| `t.add_column(pt.Column(...))`|
| Rename a column| `t.rename_column('col_name', 'new_col_name')`|
| Drop a column| `t.drop_column('col_name')`|
| Undo the last update operation (add/rename/drop column or insert)| `t.revert()`|

### Querying a table

|Action|Code|
|----|----|
| Look at 10 rows | `t.show(10)` |
| Look at all rows | `t.show(0)` |
| Look at row for frame 15 | `t[t.frame_idx == 15].show()` |
| Look at rows before index 15 | `t[t.frame_idx < 15].show(0)` |
| Look at rows before index 15 with RGB frames | `t[(t.frame_idx < 15) & (t.frame.mode == 'RGB')].show(0)` |

Pixeltable supports the standard comparison operators (`>=`, `>`, `==`, `<=`, `<`).
`== None` is the equivalent of `isna()/isnull()` in Pandas.

Boolean operators are the same as in Pandas: `&` for `and`, `|` for `or`, `~` for `not`.
They also require parentheses, for example: `(t.frame_idx < 15) & (t.frame.mode == 'RGB')`
or `~(t.frame.mode == 'RGB')`.

### Selecting and transforming columns

|Action|Code|
|----|----|
| Only retrieve the frame index and frame | `t[t.frame_idx, t.frame].show()` |
| Look at frames rotated 90 degrees | `t[t.frame.rotate(90)].show()` |
| Overlay frame with itself rotated 90 degrees | `t[pt.functions.blend(t.frame, t.frame.rotate(90))].show()` |

### Inserting data into a table
```
t.insert_rows([['/path/to/video1.mp4'], ['/path/to/video2.mp4']], columns=['video'])
```
Each row is a list of column values (do not provide values for computed columns). The
`columns` argument contains the names of columns for which values are being provided.

### Attributes and methods on image data

Images are currently represented as `PIL.Image.Image` instances in memory and support a lot of the
attributes and methods documented
[here](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image).

Available attributes are: `mode`, `height`, `width`.

Available methods are: `convert`, `crop`, `effect_spread`, `entropy`, `filter`, `getbands`, `getbbox`,
`getchannel`, `getcolors`, `getextrema`, `getpalette`, `getpixel`, `getprojection`, `histogram`,
`point`, `quantize`, `reduce`, `remap_palette`, `resize`, `rotate`, `transform`, `transpose`.

Methods can be chained, for example: `t.frame.resize((224, 224)).rotate(90).convert('L')`

### Computed columns

The values in a computed column are automatically filled when data is added:
```
t.add_column(pt.Column('frame_idx_plus_1', computed_with=(t.frame_idx + 1)))
```

### Functions

Functions can be used to transform data, both during querying as well as when data is added to a table.
```
add1 = pt.Function(return_type=pt.IntType(), param_types=[pt.IntType()], eval_fn=lambda x: x + 1)
```

For querying: `t[t.frame_idx, add1(t.frame_idx)].show()`

As a computed column: `t.add_column(pt.Column('c', computed_with=add1(t.frame_idx)))`

|Pixeltable type|Python type of compatible values|
|----|----|
| `pt.StringType()`| `str` |
| `pt.IntType()`| `int` |
| `pt.FloatType()`| `float` |
| `pt.BoolType()`| `bool` |
| `pt.TimestampType()`| `datetime.datetime` |
| `pt.JsonType()`| lists and dicts that can be converted to JSON|
| `pt.ArrayType()`| `numpy.ndarray`|
| `pt.ImageType()`| `PIL.Image.Image`|
| `pt.VideoType()`| `str` (the file path)|

### Image similarity search

In order to enable similarity on specific image columns, create those columns with `indexed=True`.
This will compute an embedding for every image and store it in a vector index.
```
c3 = pt.Column('frame', pt.ImageType(), indexed=True)
```

Assuming `img = PIL.Image.open(...)`

Similarity search: `t[t.frame.nearest(img)].show(10)`

Keyword search: `t[t.frame.matches('car')].show(10)`
