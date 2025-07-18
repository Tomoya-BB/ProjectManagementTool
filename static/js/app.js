console.log('App initialized');
document.addEventListener('DOMContentLoaded', () => {
  window.showToast = function(message, category = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const div = document.createElement('div');
    div.className = `toast align-items-center text-bg-${category === 'success' ? 'success' : category === 'error' ? 'danger' : 'info'} border-0 mb-2`;
    div.role = 'alert';
    div.innerHTML = `<div class="d-flex"><div class="toast-body">${message}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>`;
    container.appendChild(div);
    new bootstrap.Toast(div).show();
  };
  const progress = document.getElementById('progress');
  const progressValue = document.getElementById('progressValue');
  if (progress && progressValue) {
    progress.addEventListener('input', () => {
      progressValue.value = progress.value;
    });
  }

  const modal = document.getElementById('editTaskModal');
  if (modal) {
    const modalProgress = document.getElementById('modalProgress');
    const modalProgressValue = document.getElementById('modalProgressValue');
    if (modalProgress && modalProgressValue) {
      modalProgress.addEventListener('input', () => {
        modalProgressValue.value = modalProgress.value;
      });
    }

    let taskId = null;
    document.querySelectorAll('.edit-task-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        taskId = btn.dataset.id;
        modal.querySelector('input[name="name"]').value = btn.dataset.name;
        modal.querySelector('input[name="start_date"]').value = btn.dataset.start;
        modal.querySelector('input[name="end_date"]').value = btn.dataset.end;
        modal.querySelector('select[name="assignee_id"]').value = btn.dataset.assigneeId || '';
        modal.querySelector('select[name="depends_on_id"]').value = btn.dataset.dependsOnId || '';
        modal.querySelector('input[name="is_milestone"]').checked = btn.dataset.isMilestone === 'True';
        modalProgress.value = btn.dataset.progress;
        modalProgressValue.value = btn.dataset.progress;
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
      });
    });

    const saveBtn = document.getElementById('saveTaskBtn');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        fetch('/task/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: taskId,
            name: modal.querySelector('input[name="name"]').value,
            start_date: modal.querySelector('input[name="start_date"]').value,
            end_date: modal.querySelector('input[name="end_date"]').value,
            progress: modalProgress.value,
            assignee_id: modal.querySelector('select[name="assignee_id"]').value || null,
            depends_on_id: modal.querySelector('select[name="depends_on_id"]').value || null,
            is_milestone: modal.querySelector('input[name="is_milestone"]').checked
          })
        }).then(res => {
          if (res.ok) {
            location.reload();
          } else {
            showToast('Save failed', 'error');
          }
        });
      });
    }
  }

  const deleteModal = document.getElementById('deleteTaskModal');
  if (deleteModal) {
    const deleteForm = document.getElementById('deleteTaskForm');
    document.querySelectorAll('.delete-task-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        deleteForm.action = `/task/${btn.dataset.id}/delete`;
        new bootstrap.Modal(deleteModal).show();
      });
    });
  }

  const taskForm = document.getElementById('taskForm');
  if (taskForm) {
    taskForm.addEventListener('submit', (e) => {
      const start = new Date(taskForm.querySelector('input[name="start_date"]').value);
      const end = new Date(taskForm.querySelector('input[name="end_date"]').value);
      if (start > end) {
        e.preventDefault();
        showToast('Start date must be before end date', 'error');
      }
    });
  }

  const resourceForm = document.getElementById('resourceForm');
  if (resourceForm) {
    resourceForm.addEventListener('submit', (e) => {
      const util = resourceForm.querySelector('input[name="utilization"]').value;
      if (util && (util < 0 || util > 100)) {
        e.preventDefault();
        showToast('Utilization must be between 0 and 100', 'error');
      }
    });
  }
});
