from datetime import datetime
from abc import ABC, abstractmethod
from typing import Iterator, TypeVar, Generic

DataPoint = TypeVar("DataPoint")


class BaseHarvester(ABC, Generic[DataPoint]):
    """
    Base class for all Data Harvesters. Data harvesters must implement the
    'run' method.
    """

    @abstractmethod
    def run(
        self, start_date: datetime, end_date: datetime, **kwargs
    ) -> Iterator[DataPoint]:
        """
        Fetch results from the provider and yield them iteratively (streaming).
        :param start_date:
        :param end_date:
        :param kwargs:
        :return:
        """
        raise NotImplementedError
