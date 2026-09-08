<script>
  const geradoEm = new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short', timeStyle: 'short',
  }).format(new Date());
</script>

<footer class="rr">
  <span>DataHub · GPA Analytics</span>
  <span>Relatório gerado eletronicamente · {geradoEm}</span>
</footer>

<style>
  .rr {
    position: fixed; bottom: 0; left: 0; right: 0; z-index: 10;
    display: flex; justify-content: space-between; gap: 12px;
    padding: 6px 16mm;
    border-top: 1px solid #E3E8E1;
    background: #F4F6F2;
    font-size: 9px; color: #8A968A;
  }
  @media print { .rr { background: #fff; padding: 6px 12mm; } }
</style>
