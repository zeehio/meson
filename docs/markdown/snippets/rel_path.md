## Add rel_path function to get a path relative to another path

Finding what is the path to a directory relative to another directory is now possible.
For instance to find the path to `foo/lib` as if we were in `foo/bin` we now can use:
`rel_path('foo/lib', 'foo/bin')` results in `../lib`.

