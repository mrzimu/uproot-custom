# Customize factory and reader

If the built-in factories cannot reach your needs, you can implement your own `factory` and/or `reader`. 

<!-- This requires some knowledge of `ROOT`'s streaming mechanism and uproot-custom's design. -->

```{admonition} Prerequisites
---
class: note
---
Customizing own `reader` requires C++ compiler supporting `C++17` and `CMake>3.20`.
```

This chapter describes preliminary knowledge you may need when customizing your own `factory` and `reader`, and a step-by-step guide to create a template Python project for your custom implementation.

```{toctree}
---
maxdepth: 2
hidden: true
---
customize-factory-reader/bootstrap
customize-factory-reader/streamer-info
customize-factory-reader/binary-data
customize-factory-reader/reader-and-factory
customize-factory-reader/template-python-project
```
