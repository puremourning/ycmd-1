def LanguageServerSettingsForProject( project, **kwargs ):
  assert 'server_identifier' in kwargs
  assert kwargs[ 'server_identifier' ] == 'JavaCompleter'

  return {
    'java.trace.server': True,
    'java.errors.incompleteClasspath.severity': 'error',
    'java.configuration.updateBuildConfiguration': 'automatic',
  }
