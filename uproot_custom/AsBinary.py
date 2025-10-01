from __future__ import annotations

import numpy
import uproot
import uproot.extras
import uproot.interpretation


class AsBinary(uproot.interpretation.Interpretation):
    """
    Return binary data of the ``TBasket``. Pass an instance of this class
    to :ref:`uproot.behaviors.TBranch.TBranch.array` like this:

    .. code-block:: python
        binary_data = branch.array(interpretation=AsBinary())

    """

    @property
    def cache_key(self) -> str:
        return id(self)

    def basket_array(
        self,
        data,
        byte_offsets,
        basket,
        branch,
        context,
        cursor_offset,
        library,
        interp_options,
    ):
        if byte_offsets is not None:
            counts = byte_offsets[1:] - byte_offsets[:-1]
        else:
            counts = None

        if library.name == "ak":
            awkward = uproot.extras.awkward()
            if counts is not None:
                return awkward.unflatten(data, counts)
            else:
                fSize = branch.streamer.member("fSize")
                return awkward.from_numpy(data.reshape(-1, fSize))

        elif library.name == "np":
            if counts is not None:
                assert (
                    numpy.unique(counts[1:] - counts[:-1]).size == 1
                ), "The byte offsets must be uniform for NumPy arrays."

                bytes_per_event = counts[0]
                return data.reshape(-1, bytes_per_event)
            else:
                fSize = branch.streamer.member("fSize")
                return data.reshape(-1, fSize).view(">u1")
        else:
            raise ValueError(
                f"Unsupported library: {library.name}, can only use 'ak' or 'np'."
            )

    def final_array(
        self,
        basket_arrays,
        entry_start,
        entry_stop,
        entry_offsets,
        library,
        branch,
        options,
    ):
        basket_entry_starts = numpy.array(entry_offsets[:-1])
        basket_entry_stops = numpy.array(entry_offsets[1:])

        basket_start_idx = numpy.where(basket_entry_starts <= entry_start)[0].max()
        basket_end_idx = numpy.where(basket_entry_stops >= entry_stop)[0].min()

        arr_to_concat = [basket_arrays[i] for i in range(basket_start_idx, basket_end_idx + 1)]

        relative_entry_start = entry_start - basket_entry_starts[basket_start_idx]
        relative_entry_stop = entry_stop - basket_entry_starts[basket_start_idx]

        if library.name == "ak":
            awkward = uproot.extras.awkward()
            return awkward.concatenate(arr_to_concat)[relative_entry_start:relative_entry_stop]

        elif library.name == "np":
            return numpy.concatenate(arr_to_concat)[relative_entry_start:relative_entry_stop]

        else:
            raise ValueError(
                f"Unsupported library: {library.name}, can only use 'ak' or 'np'."
            )
