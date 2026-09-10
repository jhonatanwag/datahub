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
  /* Só aparece no preview em tela (/relatorio/painel/[slug] aberto direto). No
     PDF o rodapé repetido vem do page.pdf({displayHeaderFooter}) — ver
     tema-relatorio.css @media print. */
  .rr {
    display: flex; justify-content: space-between; gap: 12px;
    margin-top: 24px;
    padding: 8px 16mm 0;
    border-top: 1px solid #E3E8E1;
    font-size: 9px; color: #8A968A;
  }
</style>
