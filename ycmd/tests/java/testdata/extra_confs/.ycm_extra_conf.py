def Settings( **kwargs ):
    assert kwargs[ 'language' ] == 'java'
    return {
      'ls': { 'java.rename.enabled' : False },
      'formatting_options': { 'org.eclipse.jdt.core.formatter.lineSplit': 30, },
      # 'capabilities': {
      #   'textDocument': {
      #     'completion': {
      #       'completionItem': {
      #         'snippetSupport': True
      #       }
      #     }
      #   }
      # }
    }
