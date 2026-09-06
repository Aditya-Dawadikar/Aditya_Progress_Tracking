(function () {
  function csrfToken() {
    var input = document.querySelector('#csrf-holder [name=csrfmiddlewaretoken]');
    return input ? input.value : '';
  }

  document.querySelectorAll('.kanban').forEach(function (board) {
    var scope = board.dataset.scope;
    var scopeId = board.dataset.scopeId;
    var url = board.dataset.reorderUrl;
    var lists = board.querySelectorAll('.kanban-list');
    var group = 'goals-' + scope + '-' + scopeId;

    function sync() {
      var columns = {};
      lists.forEach(function (list) {
        columns[list.dataset.status] = Array.from(list.children).map(function (li) {
          return li.dataset.id;
        });
      });
      fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify({ scope: scope, scope_id: scopeId, columns: columns }),
      }).then(function (response) {
        if (!response.ok) {
          location.reload();
        }
      }).catch(function () {
        location.reload();
      });
    }

    lists.forEach(function (list) {
      new Sortable(list, {
        group: group,
        handle: '.drag-handle',
        animation: 150,
        ghostClass: 'goal-card-ghost',
        onEnd: sync,
      });
    });
  });
})();
