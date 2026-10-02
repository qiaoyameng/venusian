API Documentation for Venusian
==============================

.. automodule:: venusian

  .. autoclass:: Scanner

     .. automethod:: scan

     .. automethod:: collect

     .. automethod:: execute

  .. autoclass:: ScanPlan

     .. automethod:: execute

  .. autoclass:: PlannedCallback

  .. autoexception:: StaleCallbackError

  .. autoclass:: AttachInfo

  .. autofunction:: attach(wrapped, callback, category=None, name=None)

  .. autoclass:: lift

  .. autoclass:: onlyliftedfrom
