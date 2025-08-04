# Concepts

## Data tree

`ROOT` custom classes are stored in a tree-like structure. Suppose we have a custom class `Event` that contains a series of `Particle` and `Track` objects:

```C++
struct Particle {
    int pdg_id;
    double energy;
}

struct Track {
    double energy;
    double energy_error;
}

struct Event {
    int evt_num;
    std::vector<Particle> particles;
    std::vector<Track> tracks;
}
```

we can plot such data structure as:

```{mermaid}
graph LR
    Event --> evt_num
    Event --> particles
    Event --> tracks

    particles --> Particle
    Particle --> pdg_id
    Particle --> ePart[energy]

    tracks --> Track
    Track --> eTrack[energy]
    Track --> energy_error
```

with type structure:

```{mermaid}
graph LR
    Event[custom object] --> eInt[int]
    Event[custom object] --> vecPart[std::vector]
    Event[custom object] --> vecTrack[std::vector]
    vecPart --> Particle[custom object]
    vecTrack --> Track[custom object]
    Particle --> pdg_id[int]
    Particle --> ePart[double]
    Track --> eTrack[double]
    Track --> energy_error[double]
```

In `ROOT`, data is stored recursively along the tree. `ROOT` calls the `Streamer` method of the top object. In the `Streamer` method, the top object dumps its data members into binary stream in order. When data member is not a primitive type, the top object calls that data member's `Streamer` method to store its data member, recursively.

```{note}
This is a simplified explanation of how `ROOT` stores custom classes. In practice, the `Streamer` method is more complex and can handle various data types and structures.
```

In this documentation, we use "data tree" to refer to such abstract tree-like structure. The `uproot-custom` is also designed to handle such data tree.

## Reader interface

The `Reader` is introduced to handle the data tree structure. Each `Reader` is responsible for handling a specific (kinds of) node in the data tree. In the example above, we can have the following `Reader` classes:

- `BaseObjectReader`:
    - Handles `Event`, `Particle`, and `Track` object nodes.
    - Calls its elements' `Reader` to read data members.

- `STLSeqReader`:
    - Handles `std::vector` nodes.
    - Calls its element's `Reader` to read data members in a loop.
    - Stores the number of elements in each reading operation.

- `BasicTypeReader<T>`:
    - Handles primitive type nodes, such as `int`, `double`.
    - Reads a single value from the binary stream.

Besides these, all kinds of `Reader` are responsible for constructing its read-out data into an `awkward` array.

### Python and C++ parts

Since reading data from a binary stream is an efficiency-critical operation, the `Reader` is split into two parts: a C++ part and a Python part. The C++ part is responsible for reading data from the binary stream, while the Python part is responsible for combining C++ readers together and constructing the final `awkward` array.

## Reading process

The whole reading process is as follows:

1. Tree configuration generation:

    - `uproot-custom` loops over nodes in the data tree, asks each `Reader` whether it can handle the node.

    - If a `Reader` can handle the node, it returns the node configuration, which includes necessary information of creating corresponding C++ reader and combining the read-out data into an `awkward` array.

2. C++ reader generation:

    - After the tree configuration is generated, `uproot-custom` loops over the configuration and let corresponding Python reader generate C++ readers.

    - Some readers may need to generate their sub-readers recursively. For example, the `STLSeqReader` firstly generates its element reader, then generates the C++ reader with the element reader as a parameter.

    - Finally the C++ reader for the whole data tree is generated, with all sub-readers included in C++.

3. C++ reader execution:

    - The binary stream is passed to the top C++ reader.
    - The top C++ reader calls its `read` method, which reads data from the binary stream recursively by calling its sub-readers' `read` methods.
    - The read-out data is returned in numpy arrays or any Python nested containers filled with numpy arrays.

4. Reconstruction of `awkward` array:

    - The read-out data is passed to the Python part of the `Reader`.
    - The Python part combines the data into an `awkward` array with corresponding configuration information generated in the first step.