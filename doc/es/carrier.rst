#:after:carrier/carrier:section:transportistas#

Envío a transportistas
======================

En los albaranes de cliente, cuando el estado es "Empaquetado" o "Realizado" se le permite
el envío al transportista mediante la API de este. Esta acción le permite enviar el albarán
al transportista con los datos del albarán (cliente, dirección, bultos, etc).

Una vez enviado el albarán al transportista, en el albarán quedará anotado el número de referencia
asignado por el transportista. En el caso que el albarán no se ha especificado ningún
servicio, se le asignará el servicio por defecto asociado en la API del transportista.

El envío al transportista también recibiremos la etiqueta para adjuntar a nuestro paquete que
contiene los datos a enviar. El formato de la etiqueta depende del transportista y las opciones
de la API (PDF, texto, etc).

Si enviamos varios albaranes a varios transportistas, se envía según el tipo de transportista asignado
en el albarán. Si selecciona varios transportistas al disponer de varias etiquetas a imprimir, en vez
de un fichero único dispondrá de un "TAR GZ" (fichero comprimido) que lo podrá descargar y descomprimir
en su ordenador local y enviar a la impresora.

Configuración
=============

A la configuración de la API |menu_carrier_api| debe añadir los datos proporcionados por su
transportista. Deberá seleccionar el método del transportista que va relacionado. Las opciones
de esta lista depende de los módulos instalados.

.. |menu_carrier_api| tryref:: carrier_api.menu_carrier_api_form/complete_name
