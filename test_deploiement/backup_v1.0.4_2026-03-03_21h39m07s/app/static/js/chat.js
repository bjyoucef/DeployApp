$(document).ready(function () {
    var socket = io.connect('http://' + document.domain + ':' + location.port);

    // Envoyer un message lorsqu'on clique sur "Send"
    $('#send').on('click', function () {
        var message = $('#message').val();
        socket.send(message);
        $('#message').val('');  // Clear the input
    });

    // Recevoir et afficher les messages
    socket.on('message', function (msg) {
        $('#chat').append('<div>' + msg + '</div>');
        $('#chat').scrollTop($('#chat')[0].scrollHeight);  // Scroll to the bottom
    });
});
