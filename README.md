# Regenerate API docs

The following instructions are written from a UNIX perspective. For Windows,
substitute commands approparitely to run npm and/or bootprint.

To regenerate the docs, run the following from this directory. Note that
`$PATH_TO_YCMD` should be the path to the latest master of ycmd:

- `npm install --production`
  This will install the `bootprint` and `bootprint-swagger` utilities which
  parse the `yaml` and generate the API documenation
- `./node_modules/.bin/bootprint swagger $PATH_TO_YCMD/api/swagger.yaml html`
- `git add html` (etc.)
